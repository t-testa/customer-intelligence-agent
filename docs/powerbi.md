# Power BI analytical contract

Use PostgreSQL **Import mode**, refreshing after the daily snapshot/scan job. This keeps dashboard behavior deterministic and independent of model latency. Microsoft documents the [PostgreSQL connector](https://learn.microsoft.com/en-us/power-query/connectors/postgresql). Authentication and network/gateway configuration are operator tasks; no credentials belong in report files.

## Views and grain

| View | Grain | Main uses |
|---|---|---|
| `public.vw_customer_intelligence` | One current row/customer | Portfolio cards and prioritized account table |
| `public.vw_customer_history` | One row/customer/snapshot date | Customer trajectory and historical segmentation |
| `public.vw_portfolio_trend` | One row/snapshot date | Total/high-risk MRR, average risk and NPS over time |

The current/history views include ID, company, industry, CAD monthly revenue, NPS, open tickets, contract/contact dates, risk score/level/reasons, model version, pending/approved action counts and refresh timestamp. Risk is calculated in Python by the same function as `/risk`. Neither SQL views nor DAX duplicate the scoring policy.

Money uses PostgreSQL `NUMERIC(14,2)` and Power BI fixed decimal/currency. IDs, risk scores, ticket counts and action counts are whole numbers. Date columns are Date, and snapshot timestamps are timezone-aware UTC in the database (normalize to UTC before loading as Power BI Date/Time). Confidence and model narratives are intentionally excluded from financial/risk aggregates.

## Connect

1. Have an administrator create a dedicated BI login through an approved credential process and grant it membership in `cia_bi`. The group role has SELECT only on the curated views; it cannot read drafts or audit payloads.
2. In Power BI Desktop choose Get Data → PostgreSQL Database, enter the server and database, select Import, and authenticate via Data Source Settings. Use an encrypted, certificate-validated connection for Azure.
3. Load the three views, rename them `Current`, `History`, `PortfolioTrend`, and apply the documented data types.
4. Use [customer_intelligence.pq](../powerbi/customer_intelligence.pq) as a Power Query template; define text parameters `pServer` and `pDatabase`. Duplicate the query and change the view item for History and PortfolioTrend. Keep passwords in the credential store.
5. Add a Date table covering historical snapshot dates. Create a single-direction Date → History relationship. Current → History by customer ID is optional for customer selection; avoid creating a second active date path.
6. Use historical attributes in historical charts when industry/company attributes can change. A slowly changing dimension would be required for a full production semantic model.

## DAX measures

These measures target `Current`, and their full source is in [measures.dax](../powerbi/measures.dax):

```dax
Total Customers = COUNTROWS('Current')
Total MRR = SUM('Current'[monthly_revenue])
High-Risk Customers = CALCULATE([Total Customers], 'Current'[risk_level] = "HIGH")
High-Risk MRR = COALESCE(CALCULATE([Total MRR], 'Current'[risk_level] = "HIGH"), 0)
Average NPS = AVERAGE('Current'[nps_score])
High-Risk MRR Share = DIVIDE([High-Risk MRR], [Total MRR])
```

Use `SUM(PortfolioTrend[high_risk_mrr])` only with `snapshot_date` on the chart axis; summing it across dates is MRR-days, not portfolio MRR. Historical measures belong to the History table and should be constrained to one date per point. Do not mix current and historical fact rows in one total.

Display `MAX(Current[snapshot_timestamp])` as “Last snapshot (UTC)”. The refresh timestamp describes this application snapshot; it does not certify a source CRM feed's freshness. Same-day reruns upsert facts; older backfills cannot replace the newer current snapshot.

## Compact report design

The machine-readable [report-spec.json](../powerbi/report-spec.json) is an authoring specification, not a fabricated PBIP/PBIX file.

- **Portfolio page:** top cards for customers, MRR, high-risk customers, high-risk MRR and average NPS; industry and risk-level slicers; risk distribution; MRR by industry; a table sorted by risk then MRR with pending/approved action counts. Show CAD and refresh time explicitly.
- **Trends page:** high-risk MRR by snapshot date, average risk/NPS trends and a selected customer trajectory. Show missing dates as gaps. Avoid interpreting missing snapshots as zero risk.
- **Methodology tooltip:** exact risk weights, cutoff date, rule version, synthetic-data disclosure and a note that risk is a heuristic rather than churn probability.

Use a light background with dark text, blue for normal values, amber for attention and red only for high risk. Pair every color with a text label; show accessible titles and number formats. Avoid decorative gauges without decision thresholds.

## Refresh and validation

Schedule snapshots/scans before semantic-model refresh. Configure a gateway or approved cloud network path as required by your PostgreSQL deployment. Keep actual refresh credentials and schedules out of Git.

Before publishing, compare customer counts and MRR to `/customers/summary`, compare customer 3's snapshot risk to `/customers/3/risk` at the same business date, verify 40 current rows, and verify distinct `(customer_id, snapshot_date)` history keys. Inspect stale or missing snapshots instead of silently filling them. Tests already validate the database grain, upsert semantics and application-rule consistency; GUI report rendering and hosted refresh require Power BI access.
