# Shared contracts

This directory owns wire boundaries shared across components. Each contract family
must have an explicit version, a machine-readable definition, representative
fixtures, and compatibility tests before a service depends on it. Released versions
are immutable; meaningful breaking changes require a new major version.

- [API](api/README.md): HTTP request/response definitions.
- [Data](data/README.md): canonical feedback and dataset provenance.
- [Events](events/README.md): internal job/outbox and analytics projection messages.
- [Decisions](decisions/README.md): provider-independent decision results and provenance.
- [Configuration](config/README.md): typed cross-service runtime feature names.

The canonical feedback and dataset-metadata contracts are the first published
domain contracts. The scaffold health endpoint remains a process liveness check,
not a domain API. The decision question manifest belongs in
[schemas](../schemas/feedback-decision/README.md), rather than being copied into
each service.
