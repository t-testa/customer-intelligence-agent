import json
import logging
from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Lock

request_id: ContextVar[str] = ContextVar("request_id", default="job")
logger = logging.getLogger("customer_intelligence")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": record.msg,
                "request_id": request_id.get(),
                **getattr(record, "fields", {}),
            },
            default=str,
        )


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


# Only explicitly operational metadata may enter logs, even accidentally.
LOG_FIELDS = {
    "route",
    "method",
    "status",
    "latency_ms",
    "tool",
    "success",
    "rows",
    "count",
    "customer_id",
    "action_id",
    "state",
    "event_id",
    "error_type",
    "mode",
}


def event(name: str, **fields):
    logger.info(name, extra={"fields": {k: v for k, v in fields.items() if k in LOG_FIELDS}})


class Metrics:
    def __init__(self):
        self._lock = Lock()
        self._values = defaultdict(
            float,
            {
                k: 0
                for k in (
                    "requests_total",
                    "requests_failed",
                    "agent_calls_total",
                    "tool_calls_total",
                    "sql_queries_total",
                    "rag_queries_total",
                    "actions_approved_total",
                    "actions_rejected_total",
                    "intelligence_scans_total",
                    "intelligence_events_created_total",
                    "intelligence_events_deduplicated_total",
                    "intelligence_open_events",
                    "http_latency_ms_sum",
                    "agent_latency_ms_sum",
                    "errors_total",
                )
            },
        )

    def increment(self, key: str, amount: float = 1):
        with self._lock:
            self._values[key] += amount

    def set(self, key: str, value: float):
        with self._lock:
            self._values[key] = value

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._values)
