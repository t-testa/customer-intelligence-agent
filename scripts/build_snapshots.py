import argparse
from datetime import date

from src.analytics.snapshots import SnapshotService
from src.config import Settings
from src.database import Database
from src.repositories.analytics import AnalyticsRepository


def main():
    parser = argparse.ArgumentParser(
        description="Capture observed customer facts and authoritative risk into BI snapshots"
    )
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    settings = Settings()
    repository = AnalyticsRepository(Database(settings.database_url.get_secret_value()))
    print(
        {"customers_snapshotted": SnapshotService(repository).build(args.as_of or settings.today())}
    )


if __name__ == "__main__":
    main()
