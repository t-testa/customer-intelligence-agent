import hashlib
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from src.errors import ConflictError
from src.models import StrictModel
from src.observability.telemetry import event


class EventStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class IntelligenceEvent(StrictModel):
    event_id: UUID
    event_type: str
    customer_id: int
    severity: str
    status: EventStatus
    previous_risk_score: int
    current_risk_score: int
    risk_delta: int
    detected_at: datetime
    window_days: int
    baseline_date: date
    as_of: date
    dedupe_key: str
    updated_at: datetime


def severity(delta: int, current: int) -> str:
    return "CRITICAL" if delta >= 4 and current >= 6 else "HIGH" if current >= 6 else "MEDIUM"


def dedupe_key(trend) -> str:
    condition = f"risk-v1:{trend.customer_id}:{trend.window_days}:{trend.baseline_date}:{trend.previous_risk_score}:{trend.current_risk_score}"
    return hashlib.sha256(condition.encode()).hexdigest()


def authorize_event_transition(current: EventStatus, target: EventStatus):
    allowed = {
        EventStatus.OPEN: {EventStatus.ACKNOWLEDGED, EventStatus.RESOLVED},
        EventStatus.ACKNOWLEDGED: {EventStatus.RESOLVED},
        EventStatus.RESOLVED: set(),
    }
    if target not in allowed[current]:
        raise ConflictError("Invalid event transition")


class IntelligenceService:
    def __init__(self, trends, repository, metrics):
        self.trends, self.repository, self.metrics = trends, repository, metrics

    def scan(self, window_days: int = 7) -> dict:
        self.metrics.increment("intelligence_scans_total")
        created, duplicates = 0, 0
        try:
            for trend in self.trends.deteriorating(window_days):
                _, inserted = self.repository.create(
                    trend, severity(trend.risk_delta, trend.current_risk_score), dedupe_key(trend)
                )
                created += int(inserted)
                duplicates += int(not inserted)
        except Exception as exc:
            self.metrics.increment("errors_total")
            event("intelligence_scan", success=False, error_type=type(exc).__name__, count=created)
            try:
                self.repository.record_scan(created, duplicates, False)
            except Exception:
                event("scan_audit_unavailable", success=False)
            raise
        self.metrics.increment("intelligence_events_created_total", created)
        self.metrics.increment("intelligence_events_deduplicated_total", duplicates)
        open_count = self.repository.open_count()
        self.repository.record_scan(created, duplicates, True)
        self.metrics.set("intelligence_open_events", open_count)
        event("intelligence_scan", count=created, success=True)
        return {"created": created, "deduplicated": duplicates, "open_events": open_count}
