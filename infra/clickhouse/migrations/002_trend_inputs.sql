ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS decision_time Nullable(DateTime64(3, 'UTC')) AFTER decision_id;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS source_provider_id Nullable(String) AFTER decision_time;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS source_dataset_name Nullable(String) AFTER source_provider_id;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS source_dataset_version Nullable(String) AFTER source_dataset_name;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS primary_topic_accepted_positive Nullable(UInt8)
    AFTER primary_topic_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS overall_experience_accepted_positive Nullable(UInt8)
    AFTER overall_experience_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS delivery_experience_accepted_positive Nullable(UInt8)
    AFTER delivery_experience_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS support_experience_accepted_positive Nullable(UInt8)
    AFTER support_experience_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS product_defect_accepted_positive Nullable(UInt8)
    AFTER product_defect_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS actionable_accepted_positive Nullable(UInt8)
    AFTER actionable_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS severity_accepted_positive Nullable(UInt8)
    AFTER severity_eligible;

ALTER TABLE feedback_intelligence.signal_facts
    ADD COLUMN IF NOT EXISTS resolution_accepted_positive Nullable(UInt8)
    AFTER resolution_eligible;

CREATE OR REPLACE VIEW feedback_intelligence.daily_detector_inputs AS
WITH
    projection_retries_deduplicated AS
    (
        SELECT *
        FROM
        (
            SELECT
                *,
                row_number() OVER
                (
                    PARTITION BY projection_id
                    ORDER BY projected_at DESC, event_id DESC
                ) AS projection_retry_rank
            FROM feedback_intelligence.signal_facts
        )
        WHERE projection_retry_rank = 1
    ),
    latest_decisions_by_cohort AS
    (
        SELECT *
        FROM
        (
            SELECT
                *,
                row_number() OVER
                (
                    PARTITION BY
                        source_provider_id,
                        source_dataset_name,
                        source_dataset_version,
                        schema_version,
                        model_version,
                        policy_version,
                        feedback_id
                    ORDER BY decision_time DESC, decision_id DESC
                ) AS decision_rank
            FROM projection_retries_deduplicated
            WHERE policy_status = 'active'
              AND policy_version IS NOT NULL
              AND decision_time IS NOT NULL
              AND source_provider_id IS NOT NULL
              AND source_provider_id != ''
              AND source_dataset_name IS NOT NULL
              AND source_dataset_name != ''
              AND source_dataset_version IS NOT NULL
              AND source_dataset_version != ''
        )
        WHERE decision_rank = 1
    ),
    normalized_signals AS
    (
        SELECT
            toDate(event_time) AS day,
            assumeNotNull(source_provider_id) AS source_provider_id,
            assumeNotNull(source_dataset_name) AS source_dataset_name,
            assumeNotNull(source_dataset_version) AS source_dataset_version,
            schema_version,
            model_version,
            assumeNotNull(policy_version) AS policy_version,
            ifNull(product_id, '') AS product_id,
            ifNull(product_family, '') AS product_family,
            source_type,
            locale,
            feedback_id,
            tupleElement(detector_signal, 1) AS signal_key,
            tupleElement(detector_signal, 2) AS signal_value,
            tupleElement(detector_signal, 3) AS signal_eligible,
            tupleElement(detector_signal, 4) AS accepted_positive_flag
        FROM latest_decisions_by_cohort
        ARRAY JOIN
        [
            tuple(
                'primary_topic',
                CAST(primary_topic, 'Nullable(String)'),
                primary_topic_eligible,
                primary_topic_accepted_positive
            ),
            tuple(
                'overall_negative',
                CAST('negative', 'Nullable(String)'),
                overall_experience_eligible,
                overall_experience_accepted_positive
            ),
            tuple(
                'delivery_negative',
                CAST('negative', 'Nullable(String)'),
                delivery_experience_eligible,
                delivery_experience_accepted_positive
            ),
            tuple(
                'support_negative',
                CAST('negative', 'Nullable(String)'),
                support_experience_eligible,
                support_experience_accepted_positive
            ),
            tuple(
                'product_defect',
                CAST('true', 'Nullable(String)'),
                product_defect_eligible,
                product_defect_accepted_positive
            ),
            tuple(
                'actionable',
                CAST('true', 'Nullable(String)'),
                actionable_eligible,
                actionable_accepted_positive
            ),
            tuple(
                'severity',
                CAST(NULL, 'Nullable(String)'),
                severity_eligible,
                severity_accepted_positive
            ),
            tuple(
                'resolution',
                CAST(resolution_status, 'Nullable(String)'),
                resolution_eligible,
                resolution_accepted_positive
            )
        ] AS detector_signal
    )
SELECT
    day,
    source_provider_id,
    source_dataset_name,
    source_dataset_version,
    schema_version,
    model_version,
    policy_version,
    product_id,
    product_family,
    source_type,
    locale,
    signal_key,
    signal_value,
    toUInt64(count()) AS eligible_feedback,
    toUInt64(countIf(accepted_positive_flag = 1)) AS accepted_positive
FROM normalized_signals
WHERE signal_eligible = 1
  AND accepted_positive_flag IN (0, 1)
GROUP BY
    day,
    source_provider_id,
    source_dataset_name,
    source_dataset_version,
    schema_version,
    model_version,
    policy_version,
    product_id,
    product_family,
    source_type,
    locale,
    signal_key,
    signal_value;
