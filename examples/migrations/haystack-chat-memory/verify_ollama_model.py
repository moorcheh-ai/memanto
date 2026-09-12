"""Fail-closed verification of the Ollama model digest used by this example."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def model_digest(host: str, model: str) -> str:
    request = Request(f"{host.rstrip('/')}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not inspect Ollama models: {exc}") from exc
    for entry in payload.get("models", []):
        if entry.get("name") in {model, f"{model}:latest"}:
            digest = entry.get("digest")
            if isinstance(digest, str) and digest:
                return digest
    raise RuntimeError(f"Ollama model {model!r} is not installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="all-minilm")
    parser.add_argument("--digest", required=True)
    args = parser.parse_args()
    actual = model_digest(args.host, args.model)
    if actual != args.digest:
        raise SystemExit(
            f"Refusing to continue: {args.model} digest {actual} != expected {args.digest}"
        )
    print(f"Verified {args.model} digest {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
