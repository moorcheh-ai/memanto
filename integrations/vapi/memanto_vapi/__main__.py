"""``memanto-vapi`` command line: run the webhook or print tool definitions."""

from __future__ import annotations

import argparse
import json
import os
import sys


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"memanto-vapi: environment variable {name} is required")
    return value


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from memanto.cli.client.sdk_client import SdkClient
    from memanto_vapi.memory import SCOPES, VapiMemory
    from memanto_vapi.webhook import create_app

    scope = os.environ.get("MEMANTO_VAPI_SCOPE", "shared").strip() or "shared"
    if scope not in SCOPES:
        sys.exit(f"memanto-vapi: MEMANTO_VAPI_SCOPE must be one of {', '.join(SCOPES)}")
    memory = VapiMemory(
        SdkClient(api_key=_require_env("MOORCHEH_API_KEY")),
        agent_id=_require_env("MEMANTO_VAPI_AGENT_ID"),
        scope=scope,  # type: ignore[arg-type]
        caller_salt=(
            _require_env("MEMANTO_VAPI_CALLER_SALT") if scope == "caller" else None
        ),
    )
    app = create_app(
        memory,
        secret=_require_env("MEMANTO_VAPI_SECRET"),
        assistant_id=os.environ.get("MEMANTO_VAPI_ASSISTANT_ID", "").strip() or None,
    )
    uvicorn.run(app, host=args.host, port=args.port)


def _tools(args: argparse.Namespace) -> None:
    from memanto_vapi.tools import tool_definitions

    print(
        json.dumps(
            tool_definitions(
                args.server_url, scope=args.scope, credential_id=args.credential_id
            ),
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="memanto-vapi")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser(
        "serve",
        help="Run the webhook (configured by MOORCHEH_API_KEY, MEMANTO_VAPI_* env vars).",
    )
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    serve.set_defaults(handler=_serve)

    tools = commands.add_parser(
        "tools", help="Print the Vapi tool definitions as JSON for POST /tool."
    )
    tools.add_argument("--server-url", required=True)
    tools.add_argument("--scope", choices=("shared", "caller"), default="shared")
    tools.add_argument("--credential-id")
    tools.set_defaults(handler=_tools)

    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
