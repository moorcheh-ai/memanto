"""ASGI request body size limiting middleware."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from memanto.app.upload_limits import (
    MAX_REQUEST_BODY_SIZE,
    MAX_UPLOAD_FILE_SIZE,
    file_too_large_detail,
)


class _RequestBodyTooLarge(Exception):
    def __init__(self, request_size: int) -> None:
        self.request_size = request_size


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies before route handlers run."""

    def __init__(
        self,
        app: ASGIApp,
        max_request_body_size: int = MAX_REQUEST_BODY_SIZE,
        max_upload_size: int = MAX_UPLOAD_FILE_SIZE,
    ) -> None:
        self.app = app
        self.max_request_body_size = max_request_body_size
        self.max_upload_size = max_upload_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                request_size = int(content_length)
            except ValueError:
                request_size = 0
            if request_size > self.max_request_body_size:
                response = self._too_large_response(request_size)
                await response(scope, receive, send)
                return

        streamed_size = 0

        async def limited_receive():
            nonlocal streamed_size

            message = await receive()
            if message["type"] == "http.request":
                streamed_size += len(message.get("body", b""))
                if streamed_size > self.max_request_body_size:
                    raise _RequestBodyTooLarge(streamed_size)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge as exc:
            response = self._too_large_response(exc.request_size)
            await response(scope, receive, send)

    def _too_large_response(self, request_size: int) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={
                "detail": file_too_large_detail(request_size, self.max_upload_size)
            },
        )
