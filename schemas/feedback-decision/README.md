# Feedback decision schemas

This is the canonical home for immutable, versioned question manifests. Questions,
primitive types, wording, and category semantics will be defined here before adapters
consume them. Do not duplicate informal decision JSON inside services.

[`1.0.0/`](1.0.0/README.md) is active and defines the first frozen taxonomy. The
shared manifest validator is [`manifest.schema.json`](manifest.schema.json).

Decision-schema, model, confidence-policy, and data-generator versions are separate.
Changing an existing question's meaning or categories is a breaking schema change;
compatible optional additions may be minor changes. Published historical manifests
must never be silently edited.
