"""ASGI request body size limiting middleware."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from memanto.app.upload_limits import (
    MAX_REQUEST_BODY_SIZE,
    MAX_UPLOAD_FILE_SIZE,
    file_too_large_detail,
)


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
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": file_too_large_detail(
                            request_size, self.max_upload_size
                        )
                    },
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
