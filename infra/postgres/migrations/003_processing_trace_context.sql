BEGIN;

ALTER TABLE feedback.processing_jobs
    ADD COLUMN IF NOT EXISTS traceparent text,
    ADD COLUMN IF NOT EXISTS tracestate text;

ALTER TABLE feedback.processing_jobs
    DROP CONSTRAINT IF EXISTS processing_jobs_traceparent_format;

ALTER TABLE feedback.processing_jobs
    ADD CONSTRAINT processing_jobs_traceparent_format CHECK (
        traceparent IS NULL
        OR traceparent ~ '^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$'
    );

ALTER TABLE feedback.outbox_events
    ADD COLUMN IF NOT EXISTS traceparent text,
    ADD COLUMN IF NOT EXISTS tracestate text;

ALTER TABLE feedback.outbox_events
    DROP CONSTRAINT IF EXISTS outbox_events_traceparent_format;

ALTER TABLE feedback.outbox_events
    ADD CONSTRAINT outbox_events_traceparent_format CHECK (
        traceparent IS NULL
        OR traceparent ~ '^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$'
    );

INSERT INTO feedback.schema_migrations(version)
VALUES ('003_processing_trace_context')
ON CONFLICT (version) DO NOTHING;

COMMIT;
