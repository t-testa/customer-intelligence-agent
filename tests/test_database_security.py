import secrets

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from scripts.provision_roles import provision
from src.agents.sql_policy import SqlExecutor
from src.database import Database
from src.errors import PolicyError
from src.observability.telemetry import Metrics


@pytest.fixture
def restricted_urls(clean_db):
    app_pw, sql_pw = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    provision(clean_db, app_pw, sql_pw, prefix="cia_test")
    base = conninfo_to_dict(clean_db._url)
    return (
        make_conninfo(**(base | {"user": "cia_test_app", "password": app_pw})),
        make_conninfo(**(base | {"user": "cia_test_analyst", "password": sql_pw})),
    )


@pytest.mark.integration
def test_readonly_executor_and_permissions(restricted_urls):
    app_url, sql_url = restricted_urls
    executor = SqlExecutor(sql_url, Metrics(), max_rows=3, expected_role="cia_test_analyst")
    result = executor.execute("SELECT * FROM customers ORDER BY customer_id")
    assert result["row_count"] == 3
    assert result["rows"][0]["customer_id"] == 1
    assert executor.execute("SELECT count(*) AS n FROM customers")["rows"][0]["n"] == 40
    with pytest.raises(PolicyError):
        SqlExecutor(app_url, Metrics()).execute("SELECT * FROM customers")
    with psycopg.connect(sql_url, autocommit=True) as conn:
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        for query in [
            "DELETE FROM customers",
            "SELECT * FROM actions",
            "CREATE TABLE evil(id int)",
            "CREATE TEMP TABLE evil(id int)",
            "SET ROLE postgres",
        ]:
            with pytest.raises(psycopg.Error):
                conn.execute(query)


@pytest.mark.integration
def test_runtime_role_can_run_workflow(restricted_urls, as_of):
    from src.analytics.snapshots import SnapshotService
    from src.repositories.actions import ActionRepository
    from src.repositories.analytics import AnalyticsRepository
    from src.services.actions import ActionState, DraftPayload

    db = Database(restricted_urls[0])
    repo = ActionRepository(db)
    action = repo.create(3, DraftPayload(subject="Review", body="Internal draft"), "reviewer")
    repo.transition(action.action_id, ActionState.APPROVED, "reviewer")
    assert (
        repo.transition(action.action_id, ActionState.EXECUTED, "reviewer").artifact
        == action.payload
    )
    assert SnapshotService(AnalyticsRepository(db)).build(as_of) == 40
    with db.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM action_audit")


@pytest.mark.integration
def test_sql_timeout_and_byte_budget(restricted_urls, clean_db):
    executor = SqlExecutor(
        restricted_urls[1], Metrics(), timeout_ms=100, expected_role="cia_test_analyst"
    )
    with clean_db.connect() as conn:
        conn.execute("LOCK TABLE customers IN ACCESS EXCLUSIVE MODE")
        with pytest.raises(PolicyError) as failure:
            executor.execute("SELECT * FROM customers")
        assert failure.value.__cause__.sqlstate == "57014"  # PostgreSQL statement cancellation
    with pytest.raises(PolicyError, match="byte budget"):
        executor.execute("SELECT '" + "x" * 3300 + "' AS large_value FROM customers")
    with pytest.raises(PolicyError):
        executor.execute("SELECT nonexistent_column FROM customers")
