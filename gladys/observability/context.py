from contextvars import ContextVar, Token

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def bind_correlation_id(value: str) -> Token[str | None]:
    return correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    correlation_id.reset(token)
