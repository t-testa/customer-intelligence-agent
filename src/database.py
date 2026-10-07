from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


class Database:
    """Short, transaction-scoped connections. No implicit DDL on API startup."""

    def __init__(self, url: str):
        self._url = url

    @contextmanager
    def connect(self):
        with psycopg.connect(self._url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET statement_timeout = '10s'")
            conn.execute("SET lock_timeout = '3s'")
            yield conn

    def healthy(self) -> bool:
        try:
            with self.connect() as conn:
                return conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
        except psycopg.Error:
            return False
