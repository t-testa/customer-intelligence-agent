# Customer Intelligence Agent — Build Plan

Baseline: `newtocode80/customer-intelligence-agent`, branch `main`, upstream `origin/main`; only README existed. Build authorized 2026-09-16. Synthetic data only.

## Implementation phases and acceptance criteria

| Phase | Deliverable | Acceptance evidence | Status |
|---|---|---|---|
| 0 | Plan, conventions, architecture | Documents exist before application code | Complete |
| 1–2 | 40 synthetic customers; validation; PostgreSQL schema and repositories | Invalid data rejected, metrics correct, initialization idempotent | Complete |
| 3–4 | Typed FastAPI and deterministic risk | DB health, 404/422 behavior, date boundaries tested | Complete |
| 5–6 | Allowlisted agent and constrained SQL | Mocked SDK protocol, abstention, adversarial SQL, real DB timeout/role/bounds tests | Complete |
| 7–8 | Notes retrieval and typed insights | 240 notes, customer filtering, cosine/top-k, source and authoritative-fact validation | Complete |
| 9–10 | Persisted approvals, audit trail, logs and metrics | Complete transition matrix, concurrent execution, immutable payload, request IDs | Complete |
| 11–14 | Docker, CI, Azure staging/CD assets | Structural checks, actionlint, compiled Bicep, local HTTP smoke tests | Assets complete; Docker/cloud execution unavailable |
| 15 | Independent deterministic/live evaluation harness | All five deterministic gates pass; live API execution remains opt-in | Complete; live quality unmeasured |
| 16–17 | Current/daily BI snapshots and curated views | Authoritative risk reuse, one row/customer/day, idempotent upsert | Complete |
| 18–19 | Trends and deduplicated persistent events | Fixed-date trend tests, concurrent dedupe, lifecycle, scheduled job template | Complete locally; Azure job not deployed |
| Final | Full validation and consultant review | Review fixes and final verification in progress | In progress |

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
- Core agent/RAG/HITL checkpoint: 93 passing tests. Analytics/role checkpoint: 104 passing tests with 87.17% source coverage.
- Expanded end-to-end and senior review checkpoint: 119 passing tests, including the real OpenAI SDK on mock HTTP transport, PostgreSQL statement timeout, byte bounds, migration checksums and failed-scan records.
- Deterministic evaluation: tool selection 16/16; SQL safety 40/40; RAG Hit@3 10/10 from six notes per customer; structured validation 14/14; action-policy matrix 16/16. Offline metrics do not claim live LLM quality.
- Both Bicep templates compile with CLI v0.47.16. Workflow actionlint v1.7.12 passes; downloaded binary checksum verified. Portable deployment structural checks pass.
- Real HTTP smoke passed for health, metrics, customer risk and a grounded customer-3 answer. A synthetic historical scan created 18 events; immediate rerun created 0 and deduplicated 18.
- Docker engine/CLI are not installed on this machine; container build and Compose startup are unexecuted locally. CI contains both checks. No hosted CI run, Azure resource deployment, live OpenAI call or authored Power BI report is claimed.

## Senior review repairs

- Isolated test role namespace (`cia_test_*`) prevents test credential rotation of application roles.
- Added migration content checksums; changed applied migrations fail safely.
- Tightened staging TLS validation by parsing connection options instead of substring matching; blank optional keys are normalized correctly and validation errors hide inputs.
- SQL failures/timeouts log only metadata; parser warnings cannot leak raw queries.
- Added real PostgreSQL timeout/byte-budget tests, SDK-wire-format tests and explicit customer-scope enforcement on model tool requests.
- Failed scans are durably recorded when the database is reachable; partial event creation is safe to retry because uniqueness is database-enforced.
- Restricted INSERT column privileges prevent the runtime role from creating already-executed actions; update privileges and triggers protect immutable payloads.
- Expanded the RAG corpus to six topics/account so Hit@3 is not trivial retrieval over only three candidates.

## Logical commit sequence / fallback log

1. `docs: record implementation plan and project conventions`
2. `feat: add synthetic data PostgreSQL foundation and customer risk API`
3. `feat: add constrained agent SQL retrieval and structured insights`
4. `feat: add auditable human approvals and operational telemetry`
5. `feat: add historical analytics trends and intelligence events`
6. `ci: add containers evaluation gates and Azure staging delivery`
7. `docs: complete runbooks build evidence and interview preparation`

If local Git metadata is not writable, this sequence is the recommended commit log; no remote commit workaround will be used.
