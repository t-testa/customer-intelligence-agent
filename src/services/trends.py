from datetime import date, timedelta
from enum import StrEnum

from src.analytics.snapshots import RISK_MODEL_VERSION
from src.models import StrictModel
from src.services.risk import calculate_risk


class TrendStatus(StrEnum):
    DETERIORATING = "DETERIORATING"
    STABLE = "STABLE"
    IMPROVING = "IMPROVING"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class CustomerTrend(StrictModel):
    customer_id: int
    as_of: date
    window_days: int
    baseline_date: date
    previous_risk_score: int | None
    current_risk_score: int
    risk_delta: int | None
    status: TrendStatus


def compare_risk(
    customer_id: int, current: int, previous: int | None, as_of: date, window_days: int
) -> CustomerTrend:
    if (
        not 1 <= window_days <= 90
        or not 0 <= current <= 8
        or (previous is not None and not 0 <= previous <= 8)
    ):
        raise ValueError("Invalid trend inputs")
    delta = current - previous if previous is not None else None
    status = (
        TrendStatus.INSUFFICIENT_HISTORY
        if delta is None
        else TrendStatus.DETERIORATING
        if delta >= 2
        else TrendStatus.IMPROVING
        if delta <= -2
        else TrendStatus.STABLE
    )
    return CustomerTrend(
        customer_id=customer_id,
        as_of=as_of,
        window_days=window_days,
        baseline_date=as_of - timedelta(days=window_days),
        previous_risk_score=previous,
        current_risk_score=current,
        risk_delta=delta,
        status=status,
    )


class TrendService:
    def __init__(self, customers, analytics, today):
        self.customers, self.analytics, self.today = customers, analytics, today

    def all(self, window_days: int = 7) -> list[CustomerTrend]:
        if not 1 <= window_days <= 90:
            raise ValueError("Window must be between one and ninety days")
        as_of = self.today()
        previous = self.analytics.history_at(as_of - timedelta(days=window_days))
        result = []
        for customer in self.customers.get_all_customers():
            baseline = previous.get(customer.customer_id)
            old_score = (
                baseline["risk_score"]
                if baseline and baseline["risk_model_version"] == RISK_MODEL_VERSION
                else None
            )
            risk = calculate_risk(customer, as_of)
            result.append(
                compare_risk(customer.customer_id, risk.risk_score, old_score, as_of, window_days)
            )
        return result

    def deteriorating(self, window_days: int = 7):
        return [t for t in self.all(window_days) if t.status == TrendStatus.DETERIORATING]
