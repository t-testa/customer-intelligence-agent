"""Explicit synthetic scenario, not reconstructed historical observations."""

from datetime import timedelta

from src.analytics.snapshots import SnapshotService, snapshot_row
from src.config import Settings
from src.database import Database
from src.repositories.analytics import AnalyticsRepository
from src.repositories.customers import CustomerRepository


def main():
    settings = Settings()
    if settings.app_env not in {"local", "test"} or settings.model_mode != "demo":
        raise ValueError("Demo history is restricted to local/test demo mode")
    db = Database(settings.database_url.get_secret_value())
    as_of = settings.today()
    baseline_date = as_of - timedelta(days=7)
    repository = AnalyticsRepository(db)
    if repository.history_at(baseline_date):
        raise ValueError("Baseline already exists; refusing to replace observed history")
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
        repository.write_rows(conn, rows)
    SnapshotService(repository).build(as_of)
    print("Inserted explicitly synthetic healthier baseline; current CRM facts preserved")


if __name__ == "__main__":
    main()
