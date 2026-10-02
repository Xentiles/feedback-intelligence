BEGIN;
CREATE SCHEMA IF NOT EXISTS workbench;
CREATE TABLE workbench.datasets (
 id uuid PRIMARY KEY, name text NOT NULL, snapshot text NOT NULL,
 status text NOT NULL DEFAULT 'ready' CHECK(status IN ('ready','deleting','deleted')),
 created_at timestamptz NOT NULL DEFAULT now(), validation jsonb NOT NULL
);
CREATE TABLE workbench.records (
 dataset_id uuid NOT NULL REFERENCES workbench.datasets(id), id uuid NOT NULL,
 position integer NOT NULL, source_id text NOT NULL, original_text text NOT NULL,
 occurred_at timestamptz, language text, channel text, rating jsonb, groups jsonb NOT NULL,
 PRIMARY KEY(dataset_id,id), UNIQUE(dataset_id,source_id)
);
CREATE TABLE workbench.templates (
 id uuid PRIMARY KEY, name text NOT NULL, revision text NOT NULL UNIQUE,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE workbench.runs (
 id uuid PRIMARY KEY, dataset_id uuid NOT NULL REFERENCES workbench.datasets(id),
 template_id uuid NOT NULL REFERENCES workbench.templates(id), snapshot jsonb NOT NULL,
 idempotency_key text NOT NULL UNIQUE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','paused','completed','cancelled','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE TABLE workbench.jobs (
 run_id uuid NOT NULL REFERENCES workbench.runs(id), record_id uuid NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','succeeded','failed','interrupted')),
 attempt integer NOT NULL DEFAULT 0, lease_token uuid, leased_until timestamptz,
 error_code text, PRIMARY KEY(run_id,record_id)
);
CREATE TABLE workbench.results (
 run_id uuid NOT NULL, record_id uuid NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(run_id,record_id),
 FOREIGN KEY(run_id,record_id) REFERENCES workbench.jobs(run_id,record_id)
);
CREATE TABLE workbench.outbox (
 id uuid PRIMARY KEY, dataset_id uuid NOT NULL, run_id uuid NOT NULL,
 record_id uuid NOT NULL, payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pending', lease_token uuid, leased_until timestamptz,
 attempt integer NOT NULL DEFAULT 0, error_code text,
 UNIQUE(run_id,record_id)
);
CREATE INDEX workbench_jobs_claim ON workbench.jobs(status,leased_until);
CREATE OR REPLACE FUNCTION workbench.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'workbench snapshots and results are immutable'; END $$;
CREATE TRIGGER template_immutable BEFORE UPDATE OR DELETE ON workbench.templates
 FOR EACH ROW EXECUTE FUNCTION workbench.immutable();
CREATE TRIGGER result_immutable BEFORE UPDATE ON workbench.results
 FOR EACH ROW EXECUTE FUNCTION workbench.immutable();
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='workbench_api') THEN CREATE ROLE workbench_api NOLOGIN; END IF;
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='workbench_worker') THEN CREATE ROLE workbench_worker NOLOGIN; END IF;
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='workbench_purger') THEN CREATE ROLE workbench_purger NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA workbench TO workbench_api,workbench_worker,workbench_purger;
GRANT SELECT,INSERT ON workbench.datasets,workbench.records,workbench.templates,workbench.runs,workbench.jobs TO workbench_api;
GRANT UPDATE ON workbench.datasets,workbench.runs,workbench.jobs TO workbench_api;
GRANT SELECT ON ALL TABLES IN SCHEMA workbench TO workbench_worker;
GRANT UPDATE ON workbench.jobs,workbench.runs,workbench.outbox TO workbench_worker;
GRANT INSERT ON workbench.results,workbench.outbox TO workbench_worker;
GRANT SELECT ON workbench.results,workbench.outbox TO workbench_api;
GRANT INSERT ON workbench.results,workbench.outbox TO workbench_api;
GRANT SELECT,DELETE ON workbench.records,workbench.results,workbench.jobs,workbench.outbox,workbench.runs TO workbench_purger;
GRANT SELECT,UPDATE ON workbench.datasets TO workbench_purger;
INSERT INTO feedback.schema_migrations(version) VALUES('006_workbench') ON CONFLICT DO NOTHING;
COMMIT;
