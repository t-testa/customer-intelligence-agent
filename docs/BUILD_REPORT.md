# Final build report

Build date: 2026-09-16. Repository: `newtocode80/customer-intelligence-agent`. Work remains on `main`, tracking `origin/main`. Local commits were created; nothing was pushed or deployed to Azure.

## Outcome and verification boundary

Implemented the requested customer intelligence application across all 19 phases. The local Python/PostgreSQL system works, tests and deterministic evaluations pass, and deployment/BI assets are prepared. **Docker startup, hosted GitHub Actions, live OpenAI quality, Azure deployment and Power BI GUI rendering were not executed in this environment.** These remaining checks are explicit; this report does not claim every target-environment acceptance criterion has been demonstrated.

## What was implemented

- Forty synthetic customer records across six industries and 240 customer-linked notes across six topics, plus reproducible generation and Pydantic validation.
- Idempotent, versioned PostgreSQL migrations with content checksums, parameterized repositories, Decimal money and owner/runtime/analyst/BI role separation.
- FastAPI customer summaries, records, low-NPS/high-risk lists, risk explanations, grounded agent answers, insights, actions, intelligence events and operational endpoints.
- One authoritative date-injected risk engine used by API, tools, analytics and trends; no competing SQL/DAX risk model.
- OpenAI Responses integration with strict tool schemas, bounded calls, unknown-tool rejection, customer-scope checks, mockable interfaces and explicitly labeled offline mode.
- Fail-closed SQL AST policy plus real PostgreSQL read-only privileges, timeout, row bounds and byte limits.
- Direct chunking, OpenAI/demo embeddings, cosine retrieval, customer filtering, source IDs and content/model-addressed cache files.
- Validated qualitative insights with authoritative attached facts, exact retrieved evidence and constrained confidence.
- Immutable stored follow-up proposals, reviewer authorization, atomic state changes, payload digests, internal artifacts and audit records; no outbound email.
- Structured safe logging, correlation IDs, counters and durable scan/open-event metrics.
- Current/day-grain history snapshots, curated BI views, deterministic trend detection, event lifecycle and concurrent-safe deduplication.
- Non-root Docker image, Compose initialization/dependency health flow, CI test/evaluation/container gates, OIDC staging workflow, compiled Bicep app/jobs and rollback/smoke scripts.
- Power Query, DAX and dashboard authoring specifications; detailed architecture, demo and deployment runbooks.

## Architecture

```text
Human/API → authenticated routes → deterministic services → repositories → PostgreSQL
                 ↓
        bounded OpenAI/demo agent → typed tool registry
                                      ├─ authoritative customer/risk/trend tools
                                      ├─ customer-filtered note retrieval
                                      └─ SQL AST validator → restricted read-only executor

Human review → stored proposal → approval → exact internal draft artifact + audit
Daily job → shared risk snapshots → historical comparison → unique persistent event
PostgreSQL curated current/history/trend views → Power BI Import
```

Module-level contracts and ten major design decisions are in [architecture.md](architecture.md).

## Repository tree

Generated credentials, the local database, embedding caches, downloaded validators and the virtual environment are ignored and omitted below.

```text
customer-intelligence-agent/
├── .github/
│   ├── dependabot.yml
│   └── workflows/{ci.yml,deploy-staging.yml}
├── data/
│   ├── customers.csv
│   ├── customer_notes/                 # 40 JSON files, 240 notes
│   └── README.md
├── docs/
│   ├── architecture.md
│   ├── deployment-azure.md
│   ├── powerbi.md
│   ├── demo.md
│   └── BUILD_REPORT.md
├── evals/
│   ├── datasets/                       # five independent case sets
│   ├── results/baseline.json
│   └── run_evals.py
├── infra/
│   ├── container-app.bicep
│   ├── jobs.bicep
│   └── staging.parameters.example.json
├── powerbi/
│   ├── customer_intelligence.pq
│   ├── measures.dax
│   └── report-spec.json
├── scripts/
│   ├── configure_local.py
│   ├── generate_data.py
│   ├── init_db.py
│   ├── provision_roles.py
│   ├── bootstrap.py
│   ├── build_snapshots.py
│   ├── seed_demo_history.py
│   ├── run_intelligence_scan.py
│   ├── smoke_test.py
│   ├── validate_assets.py
│   └── deploy_staging.sh
├── sql/
│   ├── 001_schema.sql
│   ├── 002_actions.sql
│   ├── 003_analytics_events.sql
│   └── 004_operational_integrity.sql
├── src/
│   ├── agents/                         # provider, registry, loop, SQL policy
│   ├── analytics/                      # authoritative snapshot construction
│   ├── observability/                  # safe logs and metrics
│   ├── repositories/                   # customers, actions, analytics, events
│   ├── retrieval/                      # notes, embeddings and cosine search
│   ├── routes/                         # action/event HTTP handlers
│   ├── services/                       # data, risk, insights, actions, trends, events
│   ├── api.py
│   ├── auth.py
│   ├── config.py
│   ├── database.py
│   ├── errors.py
│   ├── models.py
│   └── runtime.py
├── tests/                              # unit, SDK mock, security and real DB tests
├── .dockerignore
├── .env.example
├── .gitattributes
├── .gitignore
├── AGENTS.md
├── BUILD_PLAN.md
├── Dockerfile
├── docker-compose.yml
├── constraints.txt
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

## Test and evaluation results

Final command: `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q` with a dedicated `TEST_DATABASE_URL`.

**120 passed, 0 failed, 0 skipped. Source statement coverage: 95.54%.** Executed on Windows with Python 3.12.14 and a real isolated PostgreSQL 18 cluster. CI targets Python 3.12 and PostgreSQL 17. Two third-party Starlette deprecation warnings concern httpx/AnyIO compatibility; they do not indicate application test failures. They should be rechecked when updating constrained dependencies.

Evidence includes complete action state matrices, duplicate-execution and duplicate-event races, database-trigger immutability, parameter binding, database health, strict schema failures, unknown tools, incorrect customer scope, real SDK request serialization on mock transport, retrieval math/filtering, source validation, historical grain, same-day upserts, role permissions, real query cancellation, byte budgets and migration drift.

Deterministic results from [baseline.json](../evals/results/baseline.json):

| Measure | Passed / cases | Result | Required |
|---|---:|---:|---:|
| Tool-selection accuracy | 16 / 16 | 100% | ≥95% |
| SQL safety pass rate | 40 / 40 | 100% | 100% |
| Customer-filtered RAG Hit@3 | 10 / 10 | 100% | ≥90% |
| Structured-output validation compliance | 14 / 14 | 100% | 100% |
| Action-policy compliance | 16 / 16 | 100% | 100% |

These small regression sets measure deterministic contracts and the offline router/lexical retrieval implementation. They are **not** a claim of perfect live-model performance or statistical generalization. Optional `--live` uses real routing, embeddings and synthesis; no live run was performed.

Additional executed checks: Ruff lint/format; actionlint 1.7.12; Bash syntax; Bicep 0.47.16 compilation of both templates; deployment structural checks; local Markdown link checks; Git whitespace and ignore checks. No credentials were committed.

Live HTTP smoke passed on the local application for `/health`, `/metrics`, `/customers/3/risk`, summary and grounded customer-3 Q&A. The fixture summary was 40 customers, CAD 482,780 MRR, 51.15 mean NPS and 4.0 average open tickets. An explicitly synthetic historical scenario generated 18 deterioration events; an immediate rescan generated 0 new events and deduplicated all 18.

## Security controls and consultant review

Controls include least-privilege database roles, parsed SQL authorization, real read-only transactions, resource limits, strict typed tools, no model-accessible mutations, authenticated review, immutable payloads, transactional audit, customer-filtered evidence, safe logs, secret exclusion, HTTPS/TLS configuration and OIDC delivery. Runtime role INSERT privileges omit action/event state fields, preventing already-executed inserts through that role.

Review fixes completed before delivery:

1. Replaced raw SQL/parser logging with operational metadata only.
2. Added actual PostgreSQL cancellation and oversized-result tests instead of relying only on validator unit tests.
3. Tested the real OpenAI SDK against mocked HTTP to verify wire-format assumptions.
4. Isolated `cia_test_*` role credentials from the application roles.
5. Added migration content checksums and rejection of edited applied files.
6. Made failed scans auditable and partial scans safe to retry.
7. Enforced the explicitly requested customer ID when the model selects customer tools.
8. Fixed empty optional-key normalization and parsed TLS validation; jobs also enforce verified TLS.
9. Expanded retrieval to six notes/account so Hit@3 has meaningful candidate competition.
10. Changed CD to promote the exact saved CI image, with revision-specific smoke testing before traffic promotion.

Remaining credibility limits are stated directly: heuristic risk needs stakeholder/outcome validation; narrative entailment and confidence are not guaranteed; individual OIDC identities/tenant isolation, API rate limits, load testing, pooled DB connections and centralized metrics are needed for a real customer deployment. The current snapshot history is observed-at-run-time data, not a reconstruction of missing CRM history. No simulated evidence is presented as customer impact or live-model accuracy.

## Deployment readiness and blocked checks

| Item | State | Exact remaining step |
|---|---|---|
| Local Python/PostgreSQL | Verified | Use README commands to reproduce |
| Docker build/Compose startup | Prepared, not locally executed | Install/start Docker with Compose v2; run `docker compose up --build`, then smoke tests |
| Hosted CI | Workflow validated locally, not run on GitHub | Push commits when authorized and inspect the CI run |
| OpenAI live mode | Implemented; SDK mocked successfully | Provide `OPENAI_API_KEY`, enable `MODEL_MODE=openai`, run separate `--live` evaluations |
| Azure staging | Templates compile; no resources created | Provision approved resources/network/identities and Key Vault secrets; configure GitHub OIDC variables; follow Azure runbook |
| Power BI | Views verified; authoring assets provided | Connect Desktop/gateway with BI credential, create report and validate rendering/refresh |

No external credential was fabricated. Azure subscription choices, paid resource approval and secret values remain operator-owned. The complete [Azure runbook](deployment-azure.md) lists each secret, identity, variable, bootstrap step and rollback command.

## How to run

Fresh Docker setup:

```bash
python scripts/configure_local.py
docker compose up --build
python scripts/smoke_test.py
```

Local Python setup after providing an existing PostgreSQL owner URL and empty database:

```bash
python -m venv .venv
# Activate the virtual environment for your shell.
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m scripts.bootstrap
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

The build machine's ignored local configuration uses port 55432 and a fixed demo date. Its application and test databases are separate within an isolated, loopback-only PostgreSQL development cluster using local trust authentication. Fresh Compose setup uses generated passwords. This is local demonstration state, not a prerequisite for a fresh clone. API documentation is at `http://127.0.0.1:8000/docs` while the server is running.

## Ten design decisions

1. PostgreSQL is the sole transactional store.
2. Monetary values use Decimal and NUMERIC, serialized without binary-float conversion.
3. Business dates are injected and UTC timestamps are explicit.
4. Transparent customer-success risk rules are distinguished from churn prediction.
5. Direct tool orchestration keeps authorization understandable.
6. Deterministic answer rendering preserves authoritative values.
7. SQL uses a small AST subset plus independent database controls.
8. Direct cosine retrieval keeps the small corpus inspectable without extra infrastructure.
9. Immutable proposals and atomic transitions preserve approval semantics under races.
10. Shared risk rules and versioned daily snapshots keep API, BI and trends consistent.

## Ten interview questions

1. Which customer-success decision improves, and how would you measure retained MRR without claiming causality prematurely?
2. Which tasks need an LLM, and which facts must remain deterministic?
3. How do the tool registry and answer renderer prevent invented customer facts?
4. Why is SELECT-only SQL still dangerous, and what independently blocks damage here?
5. What does source validation establish, and what hallucinations can still pass it?
6. What do offline evaluation scores measure, and how would you build a credible live-model benchmark?
7. How does approval remain correct under concurrent execution requests?
8. How do you maintain one definition of customer risk across Python, PostgreSQL and Power BI?
9. What changes are required for multi-tenant security and higher throughput?
10. How do OIDC, tested image promotion, migrations, revision smoke checks and rollback fit together?

Answer prompts and a five-minute demonstration sequence are in [demo.md](demo.md).
