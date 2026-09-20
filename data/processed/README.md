# Local normalized imports

`feedback-data import` writes canonical JSONL, dataset metadata, and validation
reports below this directory by default. Generated imports are Git-ignored because
they may contain licensed source text or user-supplied data. The README alone is
tracked.

Provider output remains `privacy_status: uninspected`; a processed file is not safe
for external model calls until the future privacy transformation has run.
