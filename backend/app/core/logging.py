import logging
from datetime import datetime, timezone
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


class DomainEventErrorHandler(logging.Handler):
    """Mirror backend errors into the domain event journal."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        if record.name.startswith("app.services.domain_event_service"):
            return
        if getattr(record, "skip_domain_event_journal", False):
            return

        try:
            from app.services.domain_event_service import domain_event_service

            formatted_message = record.getMessage()
            exception = record.exc_info[1] if record.exc_info else None
            error_type = getattr(record, "error_type", None)
            if not error_type:
                error_type = type(exception).__name__ if exception is not None else "LoggedError"
            payload = {
                "logger": record.name,
                "level": record.levelname.lower(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            extra = {
                key: value
                for key, value in record.__dict__.items()
                if key not in StructuredFormatter._reserved and not key.startswith("_")
            }
            if extra:
                payload["log_context"] = {
                    key: value if isinstance(value, (str, int, float, bool, type(None), list, tuple, Mapping)) else str(value)
                    for key, value in extra.items()
                }
            domain_event_service.record_error(
                error_type=str(error_type),
                source=record.name,
                category=str(getattr(record, "event_category", "health")),
                event_type=str(getattr(record, "event_type", "system.error")),
                title=str(getattr(record, "event_title", formatted_message)),
                message=formatted_message,
                correlation_id=getattr(record, "correlation_id", None),
                runtime_id=getattr(record, "runtime_id", None),
                strategy_name=getattr(record, "strategy_name", getattr(record, "strategy", None)),
                instrument=getattr(record, "instrument", None),
                position_id=getattr(record, "position_id", None),
                trade_id=getattr(record, "trade_id", None),
                execution_id=getattr(record, "execution_id", None),
                actor_type=getattr(record, "actor_type", None),
                actor_id=getattr(record, "actor_id", None),
                payload_json=payload,
                created_at=datetime.fromtimestamp(record.created, tz=timezone.utc),
                exc=exception if isinstance(exception, BaseException) else None,
            )
        except Exception:
            self.handleError(record)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    error_journal_handler = DomainEventErrorHandler(level=logging.ERROR)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addHandler(error_journal_handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
