CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY CHECK (customer_id > 0),
    company TEXT NOT NULL CHECK (length(trim(company)) BETWEEN 1 AND 120),
    industry TEXT NOT NULL CHECK (length(trim(industry)) BETWEEN 1 AND 80),
    monthly_revenue NUMERIC(14,2) NOT NULL CHECK (monthly_revenue >= 0),
    contract_end DATE NOT NULL,
    support_tickets INTEGER NOT NULL CHECK (support_tickets BETWEEN 0 AND 10000),
    nps_score INTEGER NOT NULL CHECK (nps_score BETWEEN -100 AND 100),
    last_contact DATE NOT NULL
);
