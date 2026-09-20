BEGIN;

CREATE SCHEMA IF NOT EXISTS feedback;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_api') THEN
        CREATE ROLE feedback_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_worker') THEN
        CREATE ROLE feedback_worker NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_projector') THEN
        CREATE ROLE feedback_projector NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_analytics_reader') THEN
        CREATE ROLE feedback_analytics_reader NOLOGIN;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS feedback.schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS feedback.feedback_records (
    feedback_id uuid PRIMARY KEY,
    schema_version text NOT NULL,
    source_provider_id text NOT NULL,
    source_dataset_name text NOT NULL,
    source_dataset_version text NOT NULL,
    source_record_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    channel text,
    language text,
    rating jsonb,
    related_products jsonb NOT NULL DEFAULT '[]'::jsonb,
    order_id text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    operational_context jsonb,
    canonical_sha256 char(64) NOT NULL CHECK (canonical_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source_provider_id, source_record_id)
);

CREATE INDEX IF NOT EXISTS feedback_records_occurred_at_idx
    ON feedback.feedback_records (occurred_at, feedback_id);

CREATE TABLE IF NOT EXISTS feedback.restricted_feedback_text (
    feedback_id uuid PRIMARY KEY REFERENCES feedback.feedback_records(feedback_id) ON DELETE RESTRICT,
    original_text text NOT NULL CHECK (length(btrim(original_text)) > 0),
    title text,
    privacy_status text NOT NULL DEFAULT 'uninspected',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS feedback.processing_jobs (
    job_id uuid PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    feedback_id uuid NOT NULL REFERENCES feedback.feedback_records(feedback_id) ON DELETE RESTRICT,
    decision_schema_name text NOT NULL,
    decision_schema_version text NOT NULL,
    decision_schema_sha256 text NOT NULL CHECK (
        decision_schema_sha256 ~ '^sha256:[0-9a-f]{64}$'
    ),
    engine text NOT NULL,
    requested_model text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'running', 'retry_wait', 'succeeded', 'dead')
    ),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    leased_until timestamptz,
    lease_owner text,
    lease_token uuid,
    last_error_code text,
    last_error_message text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS processing_jobs_claim_idx
    ON feedback.processing_jobs (status, available_at, created_at)
    WHERE status IN ('pending', 'retry_wait', 'running');

CREATE TABLE IF NOT EXISTS feedback.decision_runs (
    decision_id uuid PRIMARY KEY,
    job_id uuid NOT NULL UNIQUE REFERENCES feedback.processing_jobs(job_id) ON DELETE RESTRICT,
    feedback_id uuid NOT NULL REFERENCES feedback.feedback_records(feedback_id) ON DELETE RESTRICT,
    decided_at timestamptz NOT NULL,
    schema_name text NOT NULL,
    schema_version text NOT NULL,
    schema_sha256 text NOT NULL CHECK (schema_sha256 ~ '^sha256:[0-9a-f]{64}$'),
    engine_provider text NOT NULL,
    recorded_provider text,
    requested_model text NOT NULL,
    resolved_model text NOT NULL,
    policy_version text,
    redacted_text_sha256 text NOT NULL CHECK (
        redacted_text_sha256 ~ '^sha256:[0-9a-f]{64}$'
    ),
    language text,
    channel text,
    request_id text,
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    input_tokens integer CHECK (input_tokens >= 0),
    output_tokens integer CHECK (output_tokens >= 0),
    trace_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS decision_runs_feedback_idx
    ON feedback.decision_runs (feedback_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS feedback.decision_answers (
    decision_id uuid NOT NULL REFERENCES feedback.decision_runs(decision_id) ON DELETE RESTRICT,
    question_id text NOT NULL,
    primitive text NOT NULL CHECK (primitive IN ('choice', 'score', 'noul')),
    answer jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (decision_id, question_id)
);

CREATE TABLE IF NOT EXISTS feedback.review_items (
    review_item_id uuid PRIMARY KEY,
    decision_id uuid NOT NULL REFERENCES feedback.decision_runs(decision_id) ON DELETE RESTRICT,
    question_id text NOT NULL,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'resolved', 'dismissed')
    ),
    assigned_to text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at timestamptz,
    UNIQUE (decision_id, question_id)
);

CREATE TABLE IF NOT EXISTS feedback.review_labels (
    review_label_id uuid PRIMARY KEY,
    review_item_id uuid NOT NULL REFERENCES feedback.review_items(review_item_id) ON DELETE RESTRICT,
    reviewer_id text NOT NULL,
    answer jsonb NOT NULL,
    rationale text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS feedback.outbox_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    event_version text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'publishing', 'published', 'retry_wait', 'dead')
    ),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 8 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    leased_until timestamptz,
    lease_owner text,
    lease_token uuid,
    last_error_code text,
    last_error_message text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz
);

CREATE INDEX IF NOT EXISTS outbox_events_claim_idx
    ON feedback.outbox_events (status, available_at, created_at)
    WHERE status IN ('pending', 'publishing', 'retry_wait');

CREATE TABLE IF NOT EXISTS feedback.projection_ledger (
    event_id uuid PRIMARY KEY REFERENCES feedback.outbox_events(event_id) ON DELETE RESTRICT,
    projection_id uuid NOT NULL UNIQUE,
    destination text NOT NULL,
    projected_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS feedback.audit_events (
    audit_id uuid PRIMARY KEY,
    event_name text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    actor text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION feedback.reject_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is immutable', TG_TABLE_NAME USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS decision_runs_immutable ON feedback.decision_runs;
CREATE TRIGGER decision_runs_immutable
    BEFORE UPDATE OR DELETE ON feedback.decision_runs
    FOR EACH ROW EXECUTE FUNCTION feedback.reject_immutable_mutation();

DROP TRIGGER IF EXISTS decision_answers_immutable ON feedback.decision_answers;
CREATE TRIGGER decision_answers_immutable
    BEFORE UPDATE OR DELETE ON feedback.decision_answers
    FOR EACH ROW EXECUTE FUNCTION feedback.reject_immutable_mutation();

DROP TRIGGER IF EXISTS review_labels_immutable ON feedback.review_labels;
CREATE TRIGGER review_labels_immutable
    BEFORE UPDATE OR DELETE ON feedback.review_labels
    FOR EACH ROW EXECUTE FUNCTION feedback.reject_immutable_mutation();

DROP TRIGGER IF EXISTS audit_events_immutable ON feedback.audit_events;
CREATE TRIGGER audit_events_immutable
    BEFORE UPDATE OR DELETE ON feedback.audit_events
    FOR EACH ROW EXECUTE FUNCTION feedback.reject_immutable_mutation();

CREATE OR REPLACE FUNCTION feedback.claim_processing_jobs(
    worker_name text,
    batch_size integer DEFAULT 1,
    lease_seconds integer DEFAULT 60
)
RETURNS SETOF feedback.processing_jobs
LANGUAGE sql
AS $$
    WITH candidates AS (
        SELECT job_id
        FROM feedback.processing_jobs
        WHERE attempt_count < max_attempts
          AND available_at <= clock_timestamp()
          AND (
              status IN ('pending', 'retry_wait')
              OR (status = 'running' AND leased_until < clock_timestamp())
          )
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(batch_size, 0)
    )
    UPDATE feedback.processing_jobs AS job
    SET status = 'running',
        attempt_count = job.attempt_count + 1,
        lease_owner = worker_name,
        lease_token = gen_random_uuid(),
        leased_until = clock_timestamp() + make_interval(secs => GREATEST(lease_seconds, 1)),
        updated_at = clock_timestamp()
    FROM candidates
    WHERE job.job_id = candidates.job_id
    RETURNING job.*
$$;

CREATE OR REPLACE FUNCTION feedback.claim_outbox_events(
    worker_name text,
    batch_size integer DEFAULT 10,
    lease_seconds integer DEFAULT 60
)
RETURNS SETOF feedback.outbox_events
LANGUAGE sql
AS $$
    WITH candidates AS (
        SELECT event_id
        FROM feedback.outbox_events
        WHERE attempt_count < max_attempts
          AND available_at <= clock_timestamp()
          AND (
              status IN ('pending', 'retry_wait')
              OR (status = 'publishing' AND leased_until < clock_timestamp())
          )
        ORDER BY created_at, event_id
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(batch_size, 0)
    )
    UPDATE feedback.outbox_events AS event
    SET status = 'publishing',
        attempt_count = event.attempt_count + 1,
        lease_owner = worker_name,
        lease_token = gen_random_uuid(),
        leased_until = clock_timestamp() + make_interval(secs => GREATEST(lease_seconds, 1)),
        updated_at = clock_timestamp()
    FROM candidates
    WHERE event.event_id = candidates.event_id
    RETURNING event.*
$$;

GRANT USAGE ON SCHEMA feedback TO
    feedback_api, feedback_worker, feedback_projector, feedback_analytics_reader;
GRANT SELECT, INSERT ON feedback.feedback_records TO feedback_api, feedback_worker;
GRANT SELECT, INSERT ON feedback.restricted_feedback_text TO feedback_api, feedback_worker;
GRANT SELECT, INSERT ON feedback.processing_jobs TO feedback_api;
GRANT SELECT, INSERT, UPDATE ON feedback.processing_jobs TO feedback_worker;
GRANT EXECUTE ON FUNCTION feedback.claim_processing_jobs(text, integer, integer)
    TO feedback_worker;
GRANT SELECT, INSERT ON feedback.decision_runs, feedback.decision_answers TO feedback_worker;
GRANT SELECT, INSERT, UPDATE ON feedback.review_items TO feedback_worker;
GRANT SELECT, INSERT ON feedback.review_labels, feedback.audit_events TO feedback_worker;
GRANT SELECT, INSERT, UPDATE ON feedback.outbox_events TO feedback_worker, feedback_projector;
GRANT SELECT, INSERT ON feedback.projection_ledger TO feedback_projector;
GRANT EXECUTE ON FUNCTION feedback.claim_outbox_events(text, integer, integer)
    TO feedback_projector;
GRANT SELECT ON feedback.feedback_records, feedback.decision_runs,
    feedback.decision_answers, feedback.review_items TO feedback_analytics_reader;

DO $$
BEGIN
    EXECUTE format(
        'GRANT feedback_api, feedback_worker, feedback_projector, feedback_analytics_reader TO %I',
        current_user
    );
END
$$;

INSERT INTO feedback.schema_migrations(version)
VALUES ('001_operational_model')
ON CONFLICT (version) DO NOTHING;

COMMIT;
