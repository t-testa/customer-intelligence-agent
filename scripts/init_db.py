"""Apply versioned SQL files once; seed only on explicit request."""

import argparse
import hashlib

from src.config import ROOT, Settings
from src.database import Database
from src.services.data import load_customers


def initialize(db: Database, seed: bool = False):
    with db.connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(71723001)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")
        for path in sorted((ROOT / "sql").glob("[0-9][0-9][0-9]_*.sql")):
            content = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode()).hexdigest()
            exists = conn.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s", (path.name,)
            ).fetchone()
            if exists and exists["checksum"] not in (None, checksum):
                raise ValueError("Applied migration was modified; create a new numbered migration")
            if not exists:
                conn.execute(content)
                conn.execute(
                    "INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)",
                    (path.name, checksum),
                )
            elif exists["checksum"] is None:
                conn.execute(
                    "UPDATE schema_migrations SET checksum=%s WHERE version=%s",
                    (checksum, path.name),
                )
        if seed:
            for customer in load_customers(ROOT / "data/customers.csv"):
                conn.execute(
                    """INSERT INTO customers (customer_id,company,industry,monthly_revenue,
                    contract_end,support_tickets,nps_score,last_contact)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (customer_id) DO NOTHING""",
                    tuple(customer.model_dump().values()),
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    url = settings.admin_database_url or settings.database_url
    initialize(Database(url.get_secret_value()), seed=args.seed)
    print(
        "Database migrations applied"
        + ("; synthetic seed inserted without overwriting existing customers" if args.seed else "")
    )


if __name__ == "__main__":
    main()
