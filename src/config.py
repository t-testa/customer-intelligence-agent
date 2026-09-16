from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr = SecretStr("postgresql://localhost/customer_intelligence")
    admin_database_url: SecretStr | None = None
    sql_database_url: SecretStr | None = None
    app_env: Literal["local", "test", "staging", "production"] = "local"
    model_mode: Literal["demo", "openai"] = "demo"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    reader_api_key: SecretStr | None = None
    reviewer_api_key: SecretStr | None = None
    business_date: date | None = None
    sql_max_rows: int = Field(default=100, ge=1, le=500)
    sql_timeout_ms: int = Field(default=1500, ge=100, le=5000)
    model_timeout_seconds: float = Field(default=30, ge=1, le=60)
    max_tool_calls: int = Field(default=6, ge=1, le=10)

    @field_validator(
        "openai_api_key",
        "reader_api_key",
        "reviewer_api_key",
        "admin_database_url",
        "sql_database_url",
        mode="before",
    )
    @classmethod
    def empty_secret_is_unset(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def validate_environment(self):
        if self.model_mode == "openai" and not (
            self.openai_api_key and self.openai_api_key.get_secret_value()
        ):
            raise ValueError("OPENAI_API_KEY is required in openai mode")
        if self.app_env in {"staging", "production"}:
            keys = [self.reader_api_key, self.reviewer_api_key]
            if any(not key or len(key.get_secret_value()) < 32 for key in keys):
                raise ValueError(
                    "Nonlocal environments require separate API keys of 32+ characters"
                )
            if self.reader_api_key == self.reviewer_api_key:
                raise ValueError("Reader and reviewer credentials must differ")
            if self.business_date:
                raise ValueError("BUSINESS_DATE overrides are for local/test demonstrations only")
            for url in (self.database_url, self.sql_database_url):
                from psycopg.conninfo import conninfo_to_dict

                try:
                    options = conninfo_to_dict(url.get_secret_value()) if url else {}
                except Exception:
                    raise ValueError("Invalid database connection configuration") from None
                if options.get("sslmode") != "verify-full":
                    raise ValueError("Nonlocal database connections require sslmode=verify-full")
        return self

    def today(self) -> date:
        return self.business_date or datetime.now(UTC).date()
