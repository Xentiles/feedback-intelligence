CREATE DATABASE IF NOT EXISTS feedback_intelligence;

CREATE TABLE IF NOT EXISTS feedback_intelligence.signal_facts
(
    projection_id UUID,
    event_id UUID,
    event_time DateTime64(3, 'UTC'),
    feedback_id UUID,
    decision_id UUID,
    product_id Nullable(String),
    product_family Nullable(String),
    source_type LowCardinality(String),
    locale LowCardinality(String),
    primary_topic Nullable(String),
    primary_topic_confidence Nullable(Float64),
    primary_topic_eligible UInt8,
    overall_negative_probability Nullable(Float64),
    overall_experience_eligible UInt8,
    delivery_negative_probability Nullable(Float64),
    delivery_experience_eligible UInt8,
    support_negative_probability Nullable(Float64),
    support_experience_eligible UInt8,
    product_defect_probability Nullable(Float64),
    product_defect_eligible UInt8,
    actionable_probability Nullable(Float64),
    actionable_eligible UInt8,
    severity_score Nullable(Float64),
    severity_eligible UInt8,
    resolution_status Nullable(String),
    resolution_eligible UInt8,
    policy_status LowCardinality(String),
    policy_version Nullable(String),
    schema_version LowCardinality(String),
    model_version LowCardinality(String),
    trace_id UUID,
    projected_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(projected_at)
PARTITION BY toYYYYMM(event_time)
ORDER BY projection_id
SETTINGS non_replicated_deduplication_window = 10000;

ALTER TABLE feedback_intelligence.signal_facts
    MODIFY SETTING non_replicated_deduplication_window = 10000;

CREATE TABLE IF NOT EXISTS feedback_intelligence.daily_signal_rollup
(
    day Date,
    product_id String,
    product_family String,
    source_type LowCardinality(String),
    locale LowCardinality(String),
    overall_denominator UInt64,
    overall_negative_probability_sum Float64,
    delivery_denominator UInt64,
    delivery_negative_probability_sum Float64,
    support_denominator UInt64,
    support_negative_probability_sum Float64,
    defect_denominator UInt64,
    defect_probability_sum Float64,
    actionable_denominator UInt64,
    actionable_probability_sum Float64,
    severity_denominator UInt64,
    severity_score_sum Float64
)
ENGINE = SummingMergeTree
ORDER BY (day, product_id, product_family, source_type, locale);

CREATE MATERIALIZED VIEW IF NOT EXISTS feedback_intelligence.daily_signal_rollup_mv
TO feedback_intelligence.daily_signal_rollup
AS
SELECT
    toDate(event_time) AS day,
    ifNull(product_id, '') AS product_id,
    ifNull(product_family, '') AS product_family,
    source_type,
    locale,
    countIf(overall_experience_eligible = 1) AS overall_denominator,
    sumIf(ifNull(overall_negative_probability, 0), overall_experience_eligible = 1)
        AS overall_negative_probability_sum,
    countIf(delivery_experience_eligible = 1) AS delivery_denominator,
    sumIf(ifNull(delivery_negative_probability, 0), delivery_experience_eligible = 1)
        AS delivery_negative_probability_sum,
    countIf(support_experience_eligible = 1) AS support_denominator,
    sumIf(ifNull(support_negative_probability, 0), support_experience_eligible = 1)
        AS support_negative_probability_sum,
    countIf(product_defect_eligible = 1) AS defect_denominator,
    sumIf(ifNull(product_defect_probability, 0), product_defect_eligible = 1)
        AS defect_probability_sum,
    countIf(actionable_eligible = 1) AS actionable_denominator,
    sumIf(ifNull(actionable_probability, 0), actionable_eligible = 1)
        AS actionable_probability_sum,
    countIf(severity_eligible = 1) AS severity_denominator,
    sumIf(ifNull(severity_score, 0), severity_eligible = 1) AS severity_score_sum
FROM feedback_intelligence.signal_facts
WHERE overall_experience_eligible = 1
   OR delivery_experience_eligible = 1
   OR support_experience_eligible = 1
   OR product_defect_eligible = 1
   OR actionable_eligible = 1
   OR severity_eligible = 1
GROUP BY day, product_id, product_family, source_type, locale;

CREATE TABLE IF NOT EXISTS feedback_intelligence.daily_topic_rollup
(
    day Date,
    product_id String,
    product_family String,
    source_type LowCardinality(String),
    locale LowCardinality(String),
    primary_topic LowCardinality(String),
    numerator UInt64
)
ENGINE = SummingMergeTree
ORDER BY (day, product_id, product_family, source_type, locale, primary_topic);

CREATE MATERIALIZED VIEW IF NOT EXISTS feedback_intelligence.daily_topic_rollup_mv
TO feedback_intelligence.daily_topic_rollup
AS
SELECT
    toDate(event_time) AS day,
    ifNull(product_id, '') AS product_id,
    ifNull(product_family, '') AS product_family,
    source_type,
    locale,
    assumeNotNull(primary_topic) AS primary_topic,
    count() AS numerator
FROM feedback_intelligence.signal_facts
WHERE primary_topic_eligible = 1 AND primary_topic IS NOT NULL
GROUP BY day, product_id, product_family, source_type, locale, primary_topic;
