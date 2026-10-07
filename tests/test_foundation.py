from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.init_db import initialize
from src.api import create_app
from src.config import Settings
from src.models import Customer
from src.repositories.customers import CustomerRepository
from src.services.data import load_customers, summarize
from src.services.risk import calculate_risk


def test_synthetic_metrics(customers):
    assert len(customers) == 40
    summary = summarize(customers)
    assert summary.total_mrr == sum(c.monthly_revenue for c in customers)
    assert summary.customer_count == 40
    assert summary.highest_revenue_customer.monthly_revenue == max(
        c.monthly_revenue for c in customers
    )
    assert len({c.industry for c in customers}) == 6


@pytest.mark.parametrize(
    "field,value",
    [
        ("customer_id", 0),
        ("monthly_revenue", "NaN"),
        ("monthly_revenue", "1.234"),
        ("nps_score", 101),
        ("support_tickets", -1),
        ("company", " "),
        ("contract_end", "not-a-date"),
        ("customer_id", "oops"),
    ],
)
def test_customer_validation(customers, field, value):
    data = customers[0].model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        Customer.model_validate(data)


def test_bad_csv(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("customer_id,company\n1,test\n")
    with pytest.raises(ValueError):
        load_customers(path)


def test_duplicate_csv(tmp_path):
    from src.config import ROOT

    lines = (ROOT / "data/customers.csv").read_text().splitlines()
    path = tmp_path / "duplicate.csv"
    path.write_text("\n".join([lines[0], lines[1], lines[1]]))
    with pytest.raises(ValueError, match="Duplicate"):
        load_customers(path)


@pytest.mark.parametrize(
    "days,nps,tickets,contact,score,level",
    [
        (61, 30, 4, 44, 0, "LOW"),
        (60, 30, 4, 44, 3, "MEDIUM"),
        (61, 29, 4, 44, 2, "LOW"),
        (61, 30, 5, 44, 2, "LOW"),
        (61, 30, 4, 45, 1, "LOW"),
        (60, 29, 5, 45, 8, "HIGH"),
        (60, 29, 4, 44, 5, "MEDIUM"),
        (60, 29, 4, 45, 6, "HIGH"),
        (-1, 30, 4, 44, 3, "MEDIUM"),
        (0, 30, 4, 44, 3, "MEDIUM"),
    ],
)
def test_risk_boundaries(customers, as_of, days, nps, tickets, contact, score, level):
    customer = customers[0].model_copy(
        update=dict(
            contract_end=as_of + timedelta(days=days),
            nps_score=nps,
            support_tickets=tickets,
            last_contact=as_of - timedelta(days=contact),
        )
    )
    result = calculate_risk(customer, as_of)
    assert (result.risk_score, result.risk_level, result.as_of) == (score, level, as_of)


@pytest.mark.integration
def test_db_idempotency_and_queries(clean_db):
    initialize(clean_db, seed=True)
    repo = CustomerRepository(clean_db)
    assert clean_db.healthy()
    assert repo.get_customer_count() == 40
    assert repo.get_total_mrr() == summarize(repo.get_all_customers()).total_mrr
    assert isinstance(repo.get_customer_by_id(3).monthly_revenue, Decimal)
    assert repo.get_average_nps() is not None
    assert all(c.nps_score < 30 for c in repo.get_low_nps_customers())
    assert sum(r["total_mrr"] for r in repo.get_revenue_by_industry()) == repo.get_total_mrr()
    # The malicious value is treated as a parameter, never parsed as SQL.
    import psycopg

    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        repo.get_customer_by_id("1 OR 1=1")
    assert repo.get_customer_count() == 40


@pytest.mark.integration
def test_api(clean_db, as_of):
    app = create_app(Settings(_env_file=None, app_env="test", business_date=as_of))
    app.state.db = clean_db
    app.state.customers = CustomerRepository(clean_db)
    with TestClient(app) as client:
        for url in [
            "/health",
            "/metrics",
            "/customers/summary",
            "/customers/3",
            "/customers/low-nps",
            "/customers/high-risk",
            "/customers/3/risk",
        ]:
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.headers["X-Request-ID"]
        assert client.get("/customers/99999").status_code == 404
        assert client.get("/customers/nope").status_code == 422
        assert client.get("/customers/low-nps?threshold=101").status_code == 422
        assert client.get("/customers/3/risk").json()["risk_score"] == 8
        assert client.get("/metrics").json()["requests_failed"] >= 3
