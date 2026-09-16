import csv
from decimal import Decimal
from pathlib import Path

from src.models import Customer, Summary


def load_customers(path: Path) -> list[Customer]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = set(Customer.model_fields)
        if not reader.fieldnames or set(reader.fieldnames) != required:
            raise ValueError("CSV columns must match the customer schema")
        customers = [Customer.model_validate(row) for row in reader]
    if not customers:
        raise ValueError("Customer dataset is empty")
    ids = [c.customer_id for c in customers]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate customer IDs")
    return customers


def summarize(customers: list[Customer]) -> Summary:
    count = len(customers)
    return Summary(
        customer_count=count,
        total_mrr=sum((c.monthly_revenue for c in customers), Decimal("0.00")),
        average_nps=sum(c.nps_score for c in customers) / count if count else None,
        average_support_tickets=sum(c.support_tickets for c in customers) / count
        if count
        else None,
        highest_revenue_customer=max(
            customers, key=lambda c: (c.monthly_revenue, -c.customer_id), default=None
        ),
    )
