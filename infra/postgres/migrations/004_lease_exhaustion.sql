BEGIN;

-- A crashed final attempt has no failure callback. Reap expired owners while
-- polling, using the same nonblocking row locks as ordinary claims.
CREATE OR REPLACE FUNCTION feedback.claim_processing_jobs(
    worker_name text,
    batch_size integer DEFAULT 1,
    lease_seconds integer DEFAULT 60
)
RETURNS SETOF feedback.processing_jobs
LANGUAGE sql
AS $$
    WITH exhausted AS (
        SELECT job_id
        FROM feedback.processing_jobs
        WHERE attempt_count >= max_attempts
          AND (
              (status = 'running' AND leased_until < clock_timestamp())
              OR status IN ('pending', 'retry_wait')
          )
        FOR UPDATE SKIP LOCKED
    ), reaped AS (
        UPDATE feedback.processing_jobs AS job
        SET status = 'dead',
            leased_until = NULL, lease_owner = NULL, lease_token = NULL,
            last_error_code = 'AttemptsExhausted',
            last_error_message = 'Processing attempts exhausted without completion',
            updated_at = clock_timestamp()
        FROM exhausted
        WHERE job.job_id = exhausted.job_id
        RETURNING job.job_id
    ), candidates AS (
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
    WITH exhausted AS (
        SELECT event_id
        FROM feedback.outbox_events
        WHERE attempt_count >= max_attempts
          AND (
              (status = 'publishing' AND leased_until < clock_timestamp())
              OR status IN ('pending', 'retry_wait')
          )
        FOR UPDATE SKIP LOCKED
    ), reaped AS (
        UPDATE feedback.outbox_events AS event
        SET status = 'dead',
            leased_until = NULL, lease_owner = NULL, lease_token = NULL,
            last_error_code = 'AttemptsExhausted',
            last_error_message = 'Projection attempts exhausted without completion',
            updated_at = clock_timestamp()
        FROM exhausted
        WHERE event.event_id = exhausted.event_id
        RETURNING event.event_id
    ), candidates AS (
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

INSERT INTO feedback.schema_migrations(version)
VALUES ('004_lease_exhaustion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
