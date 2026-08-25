from contextvars import ContextVar

correlation_id = ContextVar("correlation_id", default="-")


def get_correlation_id() -> str:
    return correlation_id.get()
