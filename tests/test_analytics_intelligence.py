from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from src.analytics.snapshots import SnapshotService, snapshot_row
from src.errors import ConflictError
from src.observability.telemetry import Metrics
from src.repositories.actions import ActionRepository
from src.repositories.analytics import AnalyticsRepository
from src.repositories.customers import CustomerRepository
from src.repositories.intelligence import EventRepository
from src.services.actions import DraftPayload
from src.services.intelligence import EventStatus, IntelligenceService, dedupe_key, severity
from src.services.risk import calculate_risk
from src.services.trends import TrendService, TrendStatus, compare_risk


@pytest.mark.parametrize(
    "old,current,status,delta",
    [
        (2, 4, "DETERIORATING", 2),
        (2, 3, "STABLE", 1),
        (2, 2, "STABLE", 0),
        (3, 2, "STABLE", -1),
        (4, 2, "IMPROVING", -2),
        (None, 8, "INSUFFICIENT_HISTORY", None),
    ],
)
def test_trends(as_of, old, current, status, delta):
    result = compare_risk(3, current, old, as_of, 7)
    assert (result.status, result.risk_delta) == (status, delta)


@pytest.mark.integration
def test_snapshots_grain_counts_and_backfill(clean_db, as_of):
    repo = AnalyticsRepository(clean_db)
    service = SnapshotService(repo)
    ActionRepository(clean_db).create(3, DraftPayload(subject="Draft", body="Review"), "human")
    assert service.build(as_of) == service.build(as_of) == 40
    current = {r["customer_id"]: r for r in repo.current()}
    assert current[3]["pending_actions"] == 1
    customer = CustomerRepository(clean_db).get_customer_by_id(3)
    assert current[3]["risk_score"] == calculate_risk(customer, as_of).risk_score
    assert len(repo.history_at(as_of)) == 40
    service.build(as_of - timedelta(days=7))
    assert repo.current()[0]["snapshot_date"] == as_of
    with clean_db.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM customer_history").fetchone()["n"] == 80
        assert len(conn.execute("SELECT * FROM vw_portfolio_trend").fetchall()) == 2


def seed_baseline(db, as_of):
    baseline_date = as_of - timedelta(days=7)
    rows = []
    for customer in CustomerRepository(db).get_all_customers():
        old = customer.model_copy(
            update={
                "support_tickets": 0,
                "nps_score": 70,
                "last_contact": baseline_date,
                "contract_end": as_of + timedelta(days=200),
            }
        )
        rows.append(snapshot_row(old, baseline_date))
    with db.connect() as conn:
        AnalyticsRepository.write_rows(conn, rows)


@pytest.mark.integration
def test_scan_dedupe_new_condition_and_lifecycle(clean_db, as_of):
    trends = TrendService(
        CustomerRepository(clean_db), AnalyticsRepository(clean_db), lambda: as_of
    )
    assert all(t.status == TrendStatus.INSUFFICIENT_HISTORY for t in trends.all())
    seed_baseline(clean_db, as_of)
    repository = EventRepository(clean_db)
    service = IntelligenceService(trends, repository, Metrics())
    first = service.scan()
    assert first["created"] > 0
    second = service.scan()
    assert second["created"] == 0 and second["deduplicated"] == first["created"]
    record = next(e for e in repository.list() if e.customer_id == 3)
    assert record.risk_delta == 8 and record.severity == "CRITICAL"
    repository.transition(record.event_id, EventStatus.ACKNOWLEDGED, "human")
    repository.transition(record.event_id, EventStatus.RESOLVED, "human")
    with pytest.raises(ConflictError):
        repository.transition(record.event_id, EventStatus.ACKNOWLEDGED, "human")
    assert service.scan()["created"] == 0
    changed = compare_risk(3, 6, 0, as_of, 7)
    new, created = repository.create(changed, severity(6, 6), dedupe_key(changed))
    assert created and new.event_id != record.event_id
    assert repository.scan_metrics()["intelligence_scans_total"] >= 3


@pytest.mark.integration
def test_concurrent_event_deduplication(clean_db, as_of):
    repository = EventRepository(clean_db)
    trend = compare_risk(3, 8, 2, as_of, 7)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: repository.create(trend, "CRITICAL", dedupe_key(trend))[1], range(4))
        )
    assert results.count(True) == 1 and results.count(False) == 3
