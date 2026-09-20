# Event contracts

`processing-job.schema.json` defines the stable identity and lifecycle shared by
ingestion and the worker. `signal-projection-event.schema.json` defines the
text-free payload stored in the PostgreSQL outbox and projected into ClickHouse.

The projection event carries eligibility per decision dimension so partial policy
acceptance remains possible. Until calibration produces an active policy, every
eligibility flag is false and ClickHouse materialised views exclude the record from
aggregates. Neither event contract contains feedback text.

These contracts do not imply a message broker. PostgreSQL row claiming uses leases
and `FOR UPDATE SKIP LOCKED`; stable UUIDs and unique constraints make ingestion,
decision persistence, and projection replay idempotent.
