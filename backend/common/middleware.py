import logging
import re
import time
import uuid

from .correlation import correlation_id

logger = logging.getLogger("burk.request")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied if _VALID_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        )
        request.correlation_id = request_id
        context_token = correlation_id.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            return response
        finally:
            correlation_id.reset(context_token)
