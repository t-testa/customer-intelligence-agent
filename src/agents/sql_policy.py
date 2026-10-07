"""Fail-closed analytical SQL subset. PostgreSQL permissions remain a second boundary."""

import hashlib
import json
import logging
import re

import psycopg
import sqlglot
from psycopg.rows import dict_row
from sqlglot import exp
from sqlglot.errors import ParseError

from src.errors import PolicyError
from src.observability.telemetry import Metrics, event

# SQLGlot warnings may contain untrusted SQL text. Application logs emit metadata only.
logging.getLogger("sqlglot").disabled = True

TABLES = {"customers", "vw_customer_intelligence", "vw_customer_history", "vw_portfolio_trend"}
NODES = {
    "Select",
    "From",
    "Table",
    "Identifier",
    "Column",
    "Star",
    "Alias",
    "Where",
    "Group",
    "Having",
    "Order",
    "Ordered",
    "Limit",
    "Literal",
    "Null",
    "Boolean",
    "Paren",
    "And",
    "Or",
    "Not",
    "EQ",
    "NEQ",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "Between",
    "In",
    "Is",
    "Like",
    "ILike",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Neg",
    "Distinct",
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
    "Round",
    "Coalesce",
}


def validate_sql(query: str, max_rows: int = 100) -> str:
    """No joins, CTEs, subqueries, casts, arbitrary functions, catalog or qualified access."""
    if not 1 <= max_rows <= 500 or not query.strip() or len(query) > 4000:
        raise PolicyError("Invalid query bounds")
    if not re.match(r"^\s*SELECT\b", query, flags=re.I):
        raise PolicyError("Only SELECT is permitted")
    # Conservative rejection also covers comment obfuscation and quoted semicolons.
    if any(token in query for token in (";", "--", "/*", "*/", "\\", "\x00")):
        raise PolicyError("Statement separators and comments are prohibited")
    try:
        parsed = sqlglot.parse(query, read="postgres")
    except (ParseError, ValueError, RecursionError) as exc:
        raise PolicyError("SQL could not be parsed") from exc
    if len(parsed) != 1 or not isinstance(parsed[0], exp.Select):
        raise PolicyError("Only a single SELECT is permitted")
    tree = parsed[0]
    if sum(1 for _ in tree.walk()) > 200:
        raise PolicyError("Query too complex")
    if any(type(node).__name__ not in NODES for node in tree.walk()):
        raise PolicyError("SQL construct is outside the approved subset")
    if len(list(tree.find_all(exp.Select))) != 1:
        raise PolicyError("Nested queries are prohibited")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name.lower() not in TABLES:
        raise PolicyError("Select from exactly one approved relation")
    if tables[0].db or tables[0].catalog or tables[0].alias:
        raise PolicyError("Qualified relations and aliases are prohibited")
    # Prevent schema-qualified function/operator tricks and column table qualifiers.
    if any(c.db or c.catalog or c.table for c in tree.find_all(exp.Column)):
        raise PolicyError("Column qualification is prohibited")
    requested = max_rows
    if tree.args.get("limit"):
        value = tree.args["limit"].expression
        if not isinstance(value, exp.Literal) or value.is_string or not str(value.this).isdigit():
            raise PolicyError("LIMIT must be a nonnegative integer")
        requested = min(int(value.this), max_rows)
    # Execute the normalized validated AST, never the original untrusted text.
    return tree.limit(requested).sql(dialect="postgres")


class SqlExecutor:
    def __init__(
        self,
        url: str | None,
        metrics: Metrics,
        max_rows=100,
        timeout_ms=1500,
        expected_role="cia_analyst",
    ):
        self.url = url
        self.metrics = metrics
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms
        if expected_role not in {"cia_analyst", "cia_test_analyst"}:
            raise ValueError("Invalid configured analyst role")
        self.expected_role = expected_role

    def execute(self, query: str) -> dict:
        self.metrics.increment("sql_queries_total")
        try:
            validated = validate_sql(query, self.max_rows)
        except PolicyError:
            event("sql_validation", success=False)
            raise
        event("sql_validation", success=True)
        if not self.url:
            raise PolicyError("SQL_DATABASE_URL with restricted cia_analyst role is required")
        with psycopg.connect(
            self.url, autocommit=True, row_factory=dict_row, connect_timeout=5
        ) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute(
                    "SELECT set_config('statement_timeout', %s, true)", (str(self.timeout_ms),)
                )
                conn.execute("SET LOCAL lock_timeout = '500ms'")
                conn.execute("SET LOCAL search_path = public, pg_catalog")
                role = conn.execute(
                    "SELECT current_user AS name, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname=current_user"
                ).fetchone()
                if role["name"] != self.expected_role or any(
                    role[k] for k in ("rolsuper", "rolcreaterole", "rolcreatedb")
                ):
                    raise PolicyError("SQL connection must use the restricted cia_analyst role")
                try:
                    with conn.cursor(name="bounded_analytics") as cursor:
                        cursor.execute(validated)
                        rows = cursor.fetchmany(self.max_rows)
                        columns = [c.name for c in cursor.description]
                except (
                    psycopg.ProgrammingError,
                    psycopg.DataError,
                    psycopg.errors.QueryCanceled,
                    psycopg.errors.LockNotAvailable,
                ) as exc:
                    self.metrics.increment("errors_total")
                    event("sql_execution", success=False, error_type=type(exc).__name__)
                    raise PolicyError("SQL execution rejected or exceeded resource limits") from exc
        if len(json.dumps(rows, default=str).encode()) > 128_000:
            raise PolicyError("Result exceeds byte budget")
        event("sql_execution", success=True, rows=len(rows))
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "row_limit": self.max_rows,
            "query_fingerprint": hashlib.sha256(validated.encode()).hexdigest(),
        }
