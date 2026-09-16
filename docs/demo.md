# Interview demonstration

Start the stack using README instructions. Default demo date is 2026-09-16. Use only synthetic data.

## Five-minute walkthrough

1. Open `/docs`. Call `/health`; show that an unavailable PostgreSQL dependency returns 503.
2. Read `/customers/summary`: 40 accounts, CAD 482,780 MRR, average NPS 51.15 and 4.0 tickets.
3. Ask `Why is customer 3 high risk?` at `/agent/ask`. Show the two tools, exact score/reasons and customer-specific sources. Explain demo versus OpenAI mode honestly.
4. Read `/customers/3/insight`. Explain the source validation, authoritative risk fields and uncalibrated confidence.
5. Create a follow-up proposal. Try to execute it before approval: 409. Inspect subject/body, approve it, execute, then inspect the audit trail. A second execution returns 409. No email was sent.
6. Run `python -m scripts.seed_demo_history` once in a fresh local demo, then `python -m scripts.run_intelligence_scan` twice. Show created counts followed by zero new events and deduplicated counts.
7. Acknowledge and resolve an intelligence event. Connect BI to the current/history views or inspect their rows in PostgreSQL.
8. Show pytest, evaluation JSON, CI and the Azure deployment diagram. Distinguish locally verified functionality from unexecuted cloud/container checks.

## PowerShell examples

```powershell
$base = 'http://127.0.0.1:8000'
Invoke-RestMethod "$base/customers/3/risk"
$question = @{ question = 'Why is customer 3 high risk?' } | ConvertTo-Json
Invoke-RestMethod "$base/agent/ask" -Method Post -ContentType 'application/json' -Body $question
$proposal = Invoke-RestMethod "$base/customers/3/actions/followup" -Method Post
$proposal.payload
Invoke-RestMethod "$base/actions/$($proposal.action_id)/approve" -Method Post
$executed = Invoke-RestMethod "$base/actions/$($proposal.action_id)/execute" -Method Post
$executed.artifact
Invoke-RestMethod "$base/actions/$($proposal.action_id)/audit"
```

In authenticated mode use `-Headers @{ Authorization = "Bearer $env:REVIEWER_API_KEY" }` for review/execution. Keep the token out of source files, screenshots and shell history.

## Ten interview questions to prepare for

1. **What business decision does this improve?** Explain account prioritization, grounded context and accountable follow-up; propose measuring retained MRR without claiming it was achieved.
2. **Why use an LLM at all?** Language interpretation and qualitative synthesis; deterministic math and state do not need one.
3. **How does the model avoid inventing customer facts?** Approved tools, typed arguments, authoritative rendering, validated citations and service-owned insight fields.
4. **Why is SELECT-only SQL still risky?** Side-effecting functions, catalog access, denial of service and permissions; describe both AST and database layers.
5. **How would you detect hallucinations?** Source/contract checks are necessary but not sufficient; add entailment review and live evaluation against a held-out corpus.
6. **What does your evaluation score actually measure?** Separate offline router/safety contracts from live-model quality, state sample counts and thresholds, and avoid claiming statistical generalization.
7. **How do you enforce human approval under concurrency?** Row locking, allowed transitions, immutable payload/digest, atomic artifact/audit writes and race tests.
8. **How do you keep Power BI consistent with the API?** Shared Python risk rules, versioned daily snapshots, declared grain and freshness measures; no duplicate DAX risk formula.
9. **How would you scale and secure this for real customers?** Individual OIDC/RBAC, tenant filtering in all tools/queries, quotas, pooling, measured retrieval indexing and managed observability.
10. **How do deployment and rollback work?** Tested SHA, GitHub OIDC, separate migration identity, candidate revision smoke checks, traffic promotion and backward-compatible schema changes.
