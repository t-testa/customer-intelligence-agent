import argparse

from src.analytics.snapshots import SnapshotService
from src.config import Settings
from src.database import Database
from src.observability.telemetry import Metrics, configure_logging
from src.repositories.analytics import AnalyticsRepository
from src.repositories.customers import CustomerRepository
from src.repositories.intelligence import EventRepository
from src.services.intelligence import IntelligenceService
from src.services.trends import TrendService


def main():
    parser = argparse.ArgumentParser(
        description="Snapshot, then detect and persist risk deterioration"
    )
    parser.add_argument("--window-days", type=int, default=7, choices=range(1, 91))
    args = parser.parse_args()
    configure_logging()
    settings = Settings()
    db = Database(settings.database_url.get_secret_value())
    analytics = AnalyticsRepository(db)
    SnapshotService(analytics).build(settings.today())
    trends = TrendService(CustomerRepository(db), analytics, settings.today)
    print(IntelligenceService(trends, EventRepository(db), Metrics()).scan(args.window_days))


if __name__ == "__main__":
    main()
