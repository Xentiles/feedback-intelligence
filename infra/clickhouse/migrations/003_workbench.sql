CREATE TABLE IF NOT EXISTS feedback_intelligence.workbench_classifications (
 projection_id UUID, dataset_id UUID, run_id UUID, record_id UUID,
 occurred_at Nullable(DateTime64(3,'UTC')), topic String, sentiment Nullable(String),
 actionable UInt8, language Nullable(String), template_revision String,
 projected_at DateTime64(3,'UTC') DEFAULT now64(3)
) ENGINE=ReplacingMergeTree(projected_at)
ORDER BY (dataset_id,run_id,record_id);
CREATE VIEW IF NOT EXISTS feedback_intelligence.workbench_effective AS
SELECT * FROM feedback_intelligence.workbench_classifications FINAL;
