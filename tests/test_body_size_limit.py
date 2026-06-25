"""Tests for request body size limiting middleware."""

import asyncio

from memanto.app.middleware.body_size_limit import RequestBodyLimitMiddleware


def test_rejects_streamed_body_without_content_length():
    """Chunked requests without Content-Length should still be limited."""
    sent_messages = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "http.request" and not message.get(
                "more_body", False
            ):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(
        app,
        max_request_body_size=5,
        max_upload_size=5,
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [],
    }
    chunks = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413
