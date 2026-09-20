# PostgreSQL operational store

Migration `001_operational_model.sql` implements the canonical workflow store:

- canonical feedback metadata and separately permissioned restricted text;
- deterministic processing jobs with leases, bounded attempts, and retry state;
- immutable decision runs and typed answer rows;
- mutable review work items plus immutable reviewer labels;
- a transactional projection outbox, projection ledger, and audit events.

`claim_processing_jobs` and `claim_outbox_events` use `FOR UPDATE SKIP LOCKED` and
expiring leases. Stable application-generated UUIDs and unique idempotency keys
make retries converge on one logical job, decision, event, and projection.

The migration creates NOLOGIN capability roles for API, worker, projector, and
analytics readers. Only API and worker roles can read restricted feedback text;
the projector has no grant on it. The local bootstrap user inherits all roles for
Compose development. Hosted environments should create separate LOGIN users and
grant only the matching role.

The PostgreSQL container runs migrations on a fresh volume. `feedback-storage
migrate` also applies missing migrations for an existing instance. Migration files
remain append-only once released.
