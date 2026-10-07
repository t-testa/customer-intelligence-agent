import os
from datetime import date

import openai
import pytest
from psycopg.conninfo import conninfo_to_dict

from scripts.init_db import initialize
from src.config import ROOT
from src.database import Database
from src.services.data import load_customers

REAL_OPENAI_INIT = openai.OpenAI.__init__


@pytest.fixture
def sdk_client_factory():
    """Real SDK serialization on a MockTransport; no network or paid calls possible."""
    import httpx

    clients = []

    def create(handler):
        transport = httpx.MockTransport(handler)
        client = openai.OpenAI.__new__(openai.OpenAI)
        REAL_OPENAI_INIT(
            client,
            api_key="synthetic-sdk-test-key",
            http_client=httpx.Client(transport=transport),
            max_retries=0,
        )
        clients.append(client)
        return client

    yield create
    for client in clients:
        client.close()


@pytest.fixture
def as_of():
    return date(2026, 9, 16)


@pytest.fixture
def customers():
    return load_customers(ROOT / "data/customers.csv")


@pytest.fixture(scope="session")
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    if not conninfo_to_dict(url).get("dbname", "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    database = Database(url)
    initialize(database, seed=True)
    return database


@pytest.fixture
def clean_db(db):
    with db.connect() as conn:
        conn.execute("TRUNCATE customers RESTART IDENTITY CASCADE")
    initialize(db, seed=True)
    return db


@pytest.fixture(autouse=True)
def no_live_openai(monkeypatch):
    """A test that accidentally uses the SDK fails instead of making a paid call."""
    import openai

    def blocked(*args, **kwargs):
        raise AssertionError("Live OpenAI calls are prohibited in pytest")

    monkeypatch.setattr(openai.OpenAI, "__init__", blocked)
