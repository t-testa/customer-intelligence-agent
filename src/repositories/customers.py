from src.database import Database
from src.errors import NotFoundError
from src.models import Customer, Summary
from src.services.data import summarize


class CustomerRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_all_customers(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
        return [Customer.model_validate(row) for row in rows]

    def get_customer_by_id(self, customer_id: int) -> Customer:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE customer_id = %s", (customer_id,)
            ).fetchone()
        if not row:
            raise NotFoundError("Customer not found")
        return Customer.model_validate(row)

    def get_customer_count(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT count(*) AS value FROM customers").fetchone()["value"]

    def get_total_mrr(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT coalesce(sum(monthly_revenue), 0) AS value FROM customers"
            ).fetchone()["value"]

    def get_average_nps(self):
        with self.db.connect() as conn:
            return conn.execute("SELECT avg(nps_score) AS value FROM customers").fetchone()["value"]

    def get_summary(self) -> Summary:
        return summarize(self.get_all_customers())

    def get_revenue_by_industry(self) -> list[dict]:
        with self.db.connect() as conn:
            return conn.execute("""SELECT industry, sum(monthly_revenue) AS total_mrr,
                count(*) AS customer_count FROM customers GROUP BY industry ORDER BY total_mrr DESC, industry""").fetchall()

    def get_low_nps_customers(self, threshold: int = 30) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers WHERE nps_score < %s ORDER BY nps_score, customer_id",
                (threshold,),
            ).fetchall()
        return [Customer.model_validate(row) for row in rows]
