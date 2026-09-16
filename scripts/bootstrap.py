"""One-shot owner task, kept separate from the unprivileged API process."""

import os

from scripts.init_db import initialize
from scripts.provision_roles import provision
from src.analytics.snapshots import SnapshotService
from src.config import Settings
from src.database import Database
from src.repositories.analytics import AnalyticsRepository


def main():
    settings = Settings()
    if not settings.admin_database_url:
        raise ValueError("ADMIN_DATABASE_URL required for bootstrap")
    owner = Database(settings.admin_database_url.get_secret_value())
    initialize(owner, seed=True)
    # Settings reads .env; load these three secret fields explicitly without logging.
    from dotenv import dotenv_values

    from src.config import ROOT

    local = dotenv_values(ROOT / ".env")
    provision(
        owner,
        os.environ.get("APP_DB_PASSWORD") or local.get("APP_DB_PASSWORD", ""),
        os.environ.get("ANALYST_DB_PASSWORD") or local.get("ANALYST_DB_PASSWORD", ""),
    )
    SnapshotService(AnalyticsRepository(Database(settings.database_url.get_secret_value()))).build(
        settings.today()
    )
    print("Migrations, synthetic seed, least-privilege roles and initial snapshot ready")


if __name__ == "__main__":
    main()
