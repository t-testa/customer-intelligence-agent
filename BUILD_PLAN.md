# Customer Intelligence Agent — Build Plan

Baseline: `newtocode80/customer-intelligence-agent`, branch `main`, upstream `origin/main`; only README existed. Build authorized 2026-09-16. Synthetic data only.

## Implementation phases and acceptance criteria

| Phase | Deliverable | Acceptance evidence | Status |
|---|---|---|---|
| 0 | Plan, conventions, architecture | Documents exist before application code | Complete |
| 1–2 | 40 synthetic customers; validation; PostgreSQL schema and repositories | Invalid data rejected, metrics correct, initialization idempotent | Complete |
| 3–4 | Typed FastAPI and deterministic risk | DB health, 404/422 behavior, date boundaries tested | Complete |
| 5–6 | Allowlisted agent and constrained SQL | Mocked tool protocol, abstention, adversarial SQL and bounded execution tests | Pending |
| 7–8 | Notes retrieval and typed insights | Customer filtering, cosine/top-k, source and authoritative-fact validation | Pending |
| 9–10 | Persisted approvals, audit trail, logs and metrics | Complete transition matrix, concurrent execution, immutable payload, request IDs | Pending |
| 11–14 | Docker, CI, Azure staging/CD assets | Config checks, container build where available, deterministic smoke test | Pending |
| 15 | Independent deterministic/live evaluation harness | SQL and action safety 100%; other thresholds enforced; JSON report | Pending |
| 16–17 | Current/daily BI snapshots and curated views | Authoritative risk reuse, one row/customer/day, idempotent upsert | Pending |
| 18–19 | Trends and deduplicated persistent events | Fixed-date trend tests, deduplication, lifecycle, scheduled scan command | Pending |
| Final | Full validation and consultant review | Tests/evals pass; weaknesses repaired; evidence and limitations recorded | Pending |

## Architecture and execution decisions

- Keep HTTP, approved tools, deterministic services, retrieval, repositories, and observability separate.
- PostgreSQL is the only application store. Unit tests use explicit fakes; integration tests use real PostgreSQL, never SQLite compatibility assumptions.
- Use Decimal money, UTC timestamps, injected business dates, and reproducible synthetic seed dates.
- Live OpenAI is opt-in; an explicitly labeled deterministic demo provider supports a complete credential-free walkthrough.
- SQL uses a parsed, deliberately small SELECT subset plus restricted database privileges, read-only transactions, statement timeouts, and row/byte limits.
- Business action approval requires a human API role, stores a payload digest, and executes exactly one internal draft in an atomic transaction.
- Keep credentials untracked. Cloud provisioning/deployment and live-model quality cannot be claimed without execution evidence.
- Stay on the user-confirmed `main`; create logical local commits if Git permissions permit. Do not push or deploy implicitly.

## Validation journal

- Baseline Git working tree was clean.
- Python 3.12.14 found in the bundled workspace runtime. PostgreSQL 18 binaries are installed. Docker is not on PATH; container execution availability will be checked.
- Official OpenAI function-calling, structured-output, and embedding documentation consulted before implementation.
- Foundation: 23 tests passed, including real PostgreSQL 18 integration on an isolated loopback test instance. No production/local pre-existing database modified.
- Environment approval allowed dependency installation and Git commits. PostgreSQL process startup required sandbox escalation; it now runs on port 55432.

## Logical commit sequence / fallback log

1. `docs: record implementation plan and project conventions`
2. `feat: add synthetic data PostgreSQL foundation and customer risk API`
3. `feat: add constrained agent SQL retrieval and structured insights`
4. `feat: add auditable human approvals and operational telemetry`
5. `feat: add historical analytics trends and intelligence events`
6. `ci: add containers evaluation gates and Azure staging delivery`
7. `docs: complete runbooks build evidence and interview preparation`

If local Git metadata is not writable, this sequence is the recommended commit log; no remote commit workaround will be used.
