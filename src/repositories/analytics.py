from datetime import UTC, date, datetime

from psycopg import sql
from psycopg.types.json import Jsonb

from src.models import Customer

SNAPSHOT_COLUMNS = (
    "customer_id",
    "company",
    "industry",
    "monthly_revenue",
    "contract_end",
    "support_tickets",
    "nps_score",
    "last_contact",
    "snapshot_date",
    "risk_score",
    "risk_level",
    "risk_reasons",
    "risk_model_version",
    "pending_actions",
    "approved_actions",
    "snapshot_timestamp",
)


class AnalyticsRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def write_rows(conn, rows: list[dict]):
        # Only static application identifiers enter SQL composition; all values are parameters.
        for table, keys in (
            ("customer_history", ("customer_id", "snapshot_date")),
            ("customer_current", ("customer_id",)),
        ):
            updates = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
                for c in SNAPSHOT_COLUMNS
                if c not in keys
            )
            query = sql.SQL(
                "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}"
            ).format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, SNAPSHOT_COLUMNS)),
                sql.SQL(", ").join(sql.Placeholder() for _ in SNAPSHOT_COLUMNS),
                sql.SQL(", ").join(map(sql.Identifier, keys)),
                updates,
            )
            if table == "customer_current":
                query += sql.SQL(" WHERE EXCLUDED.snapshot_date >= customer_current.snapshot_date")
            for row in rows:
                values = [
                    Jsonb(row[c]) if c == "risk_reasons" else row[c] for c in SNAPSHOT_COLUMNS
                ]
                conn.execute(query, values)

    def build(self, as_of: date, row_builder) -> int:
        with self.db.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            conn.execute("SELECT pg_advisory_xact_lock(71723002)")
            customers = conn.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
            counts = {
                r["customer_id"]: r
                for r in conn.execute("""SELECT customer_id,
                count(*) FILTER (WHERE status='PENDING') AS pending,
                count(*) FILTER (WHERE status='APPROVED') AS approved FROM actions GROUP BY customer_id""").fetchall()
            }
            timestamp = datetime.now(UTC)
            rows = [
                row_builder(
                    Customer.model_validate(c),
                    as_of,
                    counts.get(c["customer_id"], {}).get("pending", 0),
                    counts.get(c["customer_id"], {}).get("approved", 0),
                    timestamp,
                )
                for c in customers
            ]
            self.write_rows(conn, rows)
        return len(rows)

    def history_at(self, snapshot_date: date) -> dict[int, dict]:
        with self.db.connect() as conn:
            return {
                r["customer_id"]: r
                for r in conn.execute(
                    "SELECT * FROM customer_history WHERE snapshot_date=%s", (snapshot_date,)
                ).fetchall()
            }

    def current(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT * FROM vw_customer_intelligence ORDER BY customer_id"
            ).fetchall()
