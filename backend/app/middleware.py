"""Request correlation (Gap #8).

Every request gets an ID — accepted from the ``X-Request-ID`` header when
the caller supplies one, generated otherwise — echoed back on the
response, available to route code via :func:`get_request_id`, and attached
to the access log line with method/path/status/latency. No payloads,
queries, or headers are logged.
"""

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("repomind.access")

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "repomind_request_id", default="-"
)


def get_request_id() -> str:
    """Current request's correlation ID (``-`` outside a request)."""
    return _request_id_ctx.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = (
            request.headers.get("x-request-id", "").strip() or uuid.uuid4().hex[:16]
        )
        request.state.request_id = request_id
        token = _request_id_ctx.set(request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        elapsed_ms = (time.monotonic() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request method=%s path=%s status=%d latency_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response
