CREATE TABLE actions (
    action_id UUID PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    action_type TEXT NOT NULL CHECK (action_type = 'DRAFT_CUSTOMER_FOLLOWUP'),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','EXECUTED')),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    artifact JSONB,
    CHECK ((status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR (status <> 'PENDING' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK ((status = 'EXECUTED' AND executed_at IS NOT NULL AND artifact = payload)
        OR (status <> 'EXECUTED' AND executed_at IS NULL AND artifact IS NULL))
);
CREATE INDEX actions_customer_status ON actions(customer_id,status);

CREATE TABLE action_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id UUID NOT NULL REFERENCES actions(action_id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    request_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE FUNCTION enforce_action_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id OR NEW.action_type IS DISTINCT FROM OLD.action_type
       OR NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Action payload and identity are immutable';
    END IF;
    IF NOT ((OLD.status = 'PENDING' AND NEW.status IN ('APPROVED','REJECTED'))
         OR (OLD.status = 'APPROVED' AND NEW.status = 'EXECUTED')) THEN
        RAISE EXCEPTION 'Invalid action transition';
    END IF;
    IF OLD.status = 'APPROVED' AND (NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
        OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at) THEN
        RAISE EXCEPTION 'Approval identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER action_integrity BEFORE UPDATE ON actions FOR EACH ROW EXECUTE FUNCTION enforce_action_integrity();
