import logging

import structlog
from structlog.typing import EventDict, WrappedLogger

from gladys.observability.context import correlation_id


def _add_correlation_id(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    value = correlation_id.get()
    if value is not None:
        event_dict["correlation_id"] = value
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=level.upper(), force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation_id,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
