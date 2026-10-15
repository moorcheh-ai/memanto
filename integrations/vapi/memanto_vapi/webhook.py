"""FastAPI webhook that connects a Vapi assistant to Memanto memory."""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Request

from memanto_vapi.memory import VapiMemory

logger = logging.getLogger(__name__)


def create_router(
    memory: VapiMemory,
    *,
    secret: str,
    assistant_id: str | None = None,
    path: str = "/vapi/webhook",
) -> APIRouter:
    """Build the webhook router.

    Args:
        memory: Configured :class:`VapiMemory`.
        secret: Shared secret from the Vapi credential. Requests must send it as
            ``Authorization: Bearer <secret>`` or ``X-Vapi-Secret: <secret>``.
        assistant_id: Saved Vapi assistant to start inbound calls with. Needed
            only when a phone number sends ``assistant-request`` here.
        path: Route path for the webhook.
    """
    if not secret:
        raise ValueError("secret must not be empty; the webhook exposes agent memory")
    expected = secret.encode("utf-8")
    router = APIRouter()

    def _authorized(authorization: str | None, x_vapi_secret: str | None) -> bool:
        candidates = [x_vapi_secret or ""]
        if authorization and authorization.lower().startswith("bearer "):
            candidates.append(authorization[7:].strip())
        return any(
            hmac.compare_digest(value.encode("utf-8"), expected)
            for value in candidates
            if value
        )

    @router.post(path)
    async def vapi_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
        x_vapi_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not _authorized(authorization, x_vapi_secret):
            raise HTTPException(status_code=401, detail="Invalid Vapi webhook secret")

        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Body is not valid JSON"
            ) from exc
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            raise HTTPException(status_code=400, detail="Missing 'message' object")

        message_type = message.get("type")
        if message_type == "assistant-request":
            if not assistant_id:
                logger.error(
                    "assistant-request received but no assistant_id is configured"
                )
                return {
                    "error": "This line is not configured yet. Please call back later."
                }
            return {
                "assistantId": assistant_id,
                "assistantOverrides": await memory.build_assistant_overrides(message),
            }
        if message_type == "tool-calls":
            return await memory.handle_tool_calls(message)
        if message_type == "end-of-call-report":
            background_tasks.add_task(_retain, memory, message)
        return {}

    return router


async def _retain(memory: VapiMemory, message: dict[str, Any]) -> None:
    # Runs after Vapi already has its 200, so failures can only be logged.
    try:
        await memory.retain_call(message)
    except Exception:
        call_id = (message.get("call") or {}).get("id")
        logger.exception("Failed to retain Vapi call %s in Memanto", call_id)


def create_app(
    memory: VapiMemory,
    *,
    secret: str,
    assistant_id: str | None = None,
    path: str = "/vapi/webhook",
) -> FastAPI:
    """Standalone app: the webhook plus ``GET /health``.

    The Memanto session is activated at startup so the first call does not
    spend its ``assistant-request`` budget on activation.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(memory.ensure_ready)
        yield

    app = FastAPI(title="memanto-vapi", lifespan=lifespan)
    app.include_router(
        create_router(memory, secret=secret, assistant_id=assistant_id, path=path)
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent_id": memory.agent_id}

    return app
