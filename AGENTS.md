# Project conventions

- Python 3.12+. FastAPI/Pydantic at the API boundary; Psycopg 3 and PostgreSQL for persistence. Avoid orchestration frameworks and extra infrastructure.
- Layers: `src/api.py` and `src/routes/` handle HTTP; `src/agents/` orchestrates allowlisted tools; `src/services/` owns business rules; `src/retrieval/` handles notes; `src/repositories/` owns SQL; `src/analytics/` reuses service rules.
- Use parameterized SQL values and Decimal money. Supply business dates explicitly; store timezone-aware UTC timestamps. Keep initialization and snapshot jobs idempotent.
- Only synthetic customer data. Never commit `.env`, credentials, tokens, database files, or model caches. Never log prompts, full notes, action bodies, headers, credentials, or exception messages containing connection strings.
- Model output and retrieved text are untrusted. Validate tool arguments, structured output and source identifiers. No eval/exec, unrestricted SQL, or model-accessible approval/execution tools.
- Generated SQL must pass the AST allowlist and execute with database-enforced read-only privileges and resource limits.
- Human actions persist before approval. Require reviewer authorization; preserve the approved payload; enforce transitions atomically and record an audit trail. Execution only finalizes an internal draft; no external email.
- Commands (from repo root): `python -m pip install -r requirements-dev.txt`; `python -m scripts.init_db`; `python -m uvicorn src.api:app`; `python -m pytest`; `python evals/run_evals.py`; `python -m ruff check .`; `docker compose up --build`.
- Normal tests and CI must not contact OpenAI. Integration tests require `TEST_DATABASE_URL` pointing to a dedicated test database. Never run destructive test cleanup against an application database.
- For major changes run focused tests, then full tests and deterministic evaluations before delivery. Include negative security, race, boundary and idempotency checks. Report skipped/unavailable validation honestly.
- Update README, BUILD_PLAN and relevant runbooks when behavior changes. Use logical commits where allowed; do not push/deploy without task authorization.
