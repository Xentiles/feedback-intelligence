BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_dashboard') THEN
        CREATE ROLE feedback_dashboard NOLOGIN;
    END IF;
END
$$;

CREATE OR REPLACE VIEW feedback.dashboard_feedback_records AS
SELECT
    feedback_id,
    source_provider_id,
    source_dataset_name,
    source_dataset_version,
    source_record_id,
    occurred_at,
    channel,
    language,
    related_products
FROM feedback.feedback_records;

CREATE OR REPLACE VIEW feedback.dashboard_processing_jobs AS
SELECT job_id, feedback_id, status
FROM feedback.processing_jobs;

CREATE OR REPLACE VIEW feedback.dashboard_decision_runs AS
SELECT
    decision_id,
    job_id,
    feedback_id,
    decided_at,
    schema_name,
    schema_version,
    resolved_model,
    policy_version,
    trace_id
FROM feedback.decision_runs;

CREATE OR REPLACE VIEW feedback.dashboard_decision_answers AS
SELECT decision_id, question_id, primitive, answer
FROM feedback.decision_answers;

CREATE OR REPLACE VIEW feedback.dashboard_projection_ledger AS
SELECT
    pl.event_id,
    pl.projection_id,
    pl.destination,
    oe.aggregate_id AS decision_id,
    pl.projected_at
FROM feedback.projection_ledger pl
JOIN feedback.outbox_events oe ON oe.event_id = pl.event_id;

REVOKE ALL ON feedback.restricted_feedback_text FROM feedback_dashboard;
REVOKE ALL ON feedback.outbox_events FROM feedback_dashboard;
GRANT USAGE ON SCHEMA feedback TO feedback_dashboard;
GRANT SELECT ON
    feedback.dashboard_feedback_records,
    feedback.dashboard_processing_jobs,
    feedback.dashboard_decision_runs,
    feedback.dashboard_decision_answers,
    feedback.dashboard_projection_ledger
TO feedback_dashboard;

DO $$
BEGIN
    EXECUTE format('GRANT feedback_dashboard TO %I', current_user);
END
$$;

INSERT INTO feedback.schema_migrations(version)
VALUES ('002_dashboard_read_role')
ON CONFLICT (version) DO NOTHING;

COMMIT;
