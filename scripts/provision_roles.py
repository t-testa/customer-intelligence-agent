"""Provision restricted runtime roles using a schema-owner connection, never the API role."""

import os

from psycopg import sql

from src.config import Settings
from src.database import Database


def provision(db: Database, app_password: str, analyst_password: str, prefix: str = "cia"):
    if not app_password or not analyst_password:
        raise ValueError("APP_DB_PASSWORD and ANALYST_DB_PASSWORD must be nonempty")
    if prefix not in {"cia", "cia_test"}:
        raise ValueError("Invalid role namespace")
    app_name, analyst_name, bi_name = prefix + "_app", prefix + "_analyst", prefix + "_bi"
    with db.connect() as conn:
        for name, password in ((app_name, app_password), (analyst_name, analyst_password)):
            existing = conn.execute(
                "SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=%s",
                (name,),
            ).fetchone()
            if existing and any(existing.values()):
                raise ValueError("Refusing to reuse an administrative role")
            if not existing:
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
                    ).format(sql.Identifier(name))
                )
            # Utility DDL cannot bind parameters; Literal safely quotes the secret.
            conn.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(name), sql.Literal(password)
                )
            )
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (bi_name,)).fetchone():
            conn.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(bi_name)
                )
            )

        def role_statement(statement):
            conn.execute(
                sql.SQL(statement).format(
                    app=sql.Identifier(app_name),
                    analyst=sql.Identifier(analyst_name),
                    bi=sql.Identifier(bi_name),
                )
            )

        database_name = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        conn.execute(
            sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(database_name)
            )
        )
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        role_statement("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app}, {analyst}, {bi}")
        conn.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
        role_statement("GRANT USAGE ON SCHEMA public TO {app}, {analyst}, {bi}")
        role_statement("GRANT SELECT ON customers TO {app}, {analyst}")
        role_statement("GRANT SELECT ON actions, intelligence_events TO {app}")
        role_statement(
            "GRANT INSERT(action_id,customer_id,action_type,payload,payload_hash,created_by) ON actions TO {app}"
        )
        role_statement(
            "GRANT INSERT(event_id,event_type,customer_id,severity,previous_risk_score,current_risk_score,risk_delta,window_days,baseline_date,as_of,dedupe_key) ON intelligence_events TO {app}"
        )
        role_statement(
            "GRANT SELECT, INSERT ON action_audit, intelligence_event_audit, intelligence_scan_runs TO {app}"
        )
        role_statement(
            "GRANT UPDATE(status,reviewed_by,reviewed_at,executed_at,artifact) ON actions TO {app}"
        )
        role_statement("GRANT UPDATE(status,updated_at) ON intelligence_events TO {app}")
        role_statement(
            "GRANT SELECT, INSERT, UPDATE ON customer_current, customer_history TO {app}"
        )
        role_statement("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app}")
        role_statement(
            "GRANT SELECT ON vw_customer_intelligence, vw_customer_history, vw_portfolio_trend TO {app}, {analyst}, {bi}"
        )
        role_statement("ALTER ROLE {analyst} SET default_transaction_read_only = on")
        role_statement("ALTER ROLE {analyst} SET statement_timeout = '1500ms'")
        role_statement("ALTER ROLE {analyst} SET search_path = public, pg_catalog")


def main():
    settings = Settings()
    if not settings.admin_database_url:
        raise ValueError("ADMIN_DATABASE_URL is required for provisioning")
    provision(
        Database(settings.admin_database_url.get_secret_value()),
        os.environ["APP_DB_PASSWORD"],
        os.environ["ANALYST_DB_PASSWORD"],
    )
    print("Restricted runtime, SQL and BI privileges provisioned")


if __name__ == "__main__":
    main()
