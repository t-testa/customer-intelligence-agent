CREATE TABLE intelligence_scan_runs (
    scan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_events INTEGER NOT NULL,
    deduplicated_events INTEGER NOT NULL,
    success BOOLEAN NOT NULL
);
CREATE FUNCTION enforce_event_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - 'status' - 'updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'updated_at') THEN
        RAISE EXCEPTION 'Event facts are immutable';
    END IF;
    IF NOT ((OLD.status='OPEN' AND NEW.status IN ('ACKNOWLEDGED','RESOLVED'))
         OR (OLD.status='ACKNOWLEDGED' AND NEW.status='RESOLVED')) THEN
        RAISE EXCEPTION 'Invalid event transition';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER event_integrity BEFORE UPDATE ON intelligence_events FOR EACH ROW EXECUTE FUNCTION enforce_event_integrity();
