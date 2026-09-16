CREATE TABLE customer_history (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    snapshot_date DATE NOT NULL,
    company TEXT NOT NULL,
    industry TEXT NOT NULL,
    monthly_revenue NUMERIC(14,2) NOT NULL,
    nps_score INTEGER NOT NULL,
    support_tickets INTEGER NOT NULL,
    contract_end DATE NOT NULL,
    last_contact DATE NOT NULL,
    risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 8),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    risk_reasons JSONB NOT NULL,
    risk_model_version TEXT NOT NULL,
    pending_actions INTEGER NOT NULL,
    approved_actions INTEGER NOT NULL,
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (customer_id, snapshot_date)
);
CREATE INDEX customer_history_date ON customer_history(snapshot_date);
CREATE TABLE customer_current (LIKE customer_history INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
ALTER TABLE customer_current ADD PRIMARY KEY (customer_id);
ALTER TABLE customer_current ADD FOREIGN KEY (customer_id) REFERENCES customers(customer_id);

CREATE VIEW vw_customer_intelligence AS SELECT * FROM customer_current;
CREATE VIEW vw_customer_history AS SELECT * FROM customer_history;
CREATE VIEW vw_portfolio_trend AS
SELECT snapshot_date, count(*) AS customer_count, sum(monthly_revenue) AS total_mrr,
       count(*) FILTER (WHERE risk_level='HIGH') AS high_risk_customers,
       coalesce(sum(monthly_revenue) FILTER (WHERE risk_level='HIGH'),0) AS high_risk_mrr,
       avg(risk_score) AS average_risk_score, avg(nps_score) AS average_nps,
       max(snapshot_timestamp) AS refreshed_at
FROM customer_history GROUP BY snapshot_date;

CREATE TABLE intelligence_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type='CUSTOMER_RISK_DETERIORATION'),
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    severity TEXT NOT NULL CHECK (severity IN ('MEDIUM','HIGH','CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    previous_risk_score INTEGER NOT NULL CHECK (previous_risk_score BETWEEN 0 AND 8),
    current_risk_score INTEGER NOT NULL CHECK (current_risk_score BETWEEN 0 AND 8),
    risk_delta INTEGER NOT NULL CHECK (risk_delta >= 2 AND risk_delta=current_risk_score-previous_risk_score),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_days INTEGER NOT NULL CHECK (window_days BETWEEN 1 AND 90),
    baseline_date DATE NOT NULL,
    as_of DATE NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX intelligence_events_status ON intelligence_events(status, detected_at);
CREATE TABLE intelligence_event_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES intelligence_events(event_id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    request_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
