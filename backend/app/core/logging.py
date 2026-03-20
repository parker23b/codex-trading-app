import logging
from collections.abc import Mapping
from json import dumps


class StructuredFormatter(logging.Formatter):
    """Attach non-standard LogRecord fields as JSON for easier backend tracing."""

    _reserved = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        base_message = super().format(record)
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._reserved and not key.startswith("_")
        }
        if not extra:
            return base_message

        serializable_extra = {
            key: value if isinstance(value, (str, int, float, bool, type(None), list, tuple, Mapping)) else str(value)
            for key, value in extra.items()
        }
        return f"{base_message} {dumps(serializable_extra, sort_keys=True)}"


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
