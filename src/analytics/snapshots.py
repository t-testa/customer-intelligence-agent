from datetime import UTC, date, datetime

from src.models import Customer
from src.services.risk import calculate_risk

RISK_MODEL_VERSION = "rules-v1"


def snapshot_row(
    customer: Customer,
    as_of: date,
    pending: int = 0,
    approved: int = 0,
    timestamp: datetime | None = None,
) -> dict:
    risk = calculate_risk(customer, as_of)
    return {
        **customer.model_dump(),
        "snapshot_date": as_of,
        "risk_score": risk.risk_score,
        "risk_level": risk.risk_level.value,
        "risk_reasons": risk.reasons,
        "risk_model_version": RISK_MODEL_VERSION,
        "pending_actions": pending,
        "approved_actions": approved,
        "snapshot_timestamp": timestamp or datetime.now(UTC),
    }


class SnapshotService:
    def __init__(self, repository):
        self.repository = repository

    def build(self, as_of: date) -> int:
        # Repository owns one consistent database read and atomic write transaction.
        return self.repository.build(as_of, snapshot_row)
