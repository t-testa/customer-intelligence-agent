"""Create a local .env with random credentials without printing secrets; never overwrite."""

import argparse
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5432)
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / ".env"
    admin, app, analyst = [secrets.token_urlsafe(32) for _ in range(3)]
    content = f"""# Generated local-only credentials. Git ignores this file.
POSTGRES_PASSWORD={admin}
APP_DB_PASSWORD={app}
ANALYST_DB_PASSWORD={analyst}
DATABASE_URL=postgresql://cia_app:{app}@127.0.0.1:{args.port}/customer_intelligence
ADMIN_DATABASE_URL=postgresql://postgres:{admin}@127.0.0.1:{args.port}/customer_intelligence
SQL_DATABASE_URL=postgresql://cia_analyst:{analyst}@127.0.0.1:{args.port}/customer_intelligence
APP_ENV=local
MODEL_MODE=demo
BUSINESS_DATE=2026-09-16
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small
READER_API_KEY=
REVIEWER_API_KEY=
"""
    try:
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        raise SystemExit(".env already exists; preserved unchanged") from None
    print("Created ignored .env with random local credentials. No secret values printed.")


if __name__ == "__main__":
    main()
