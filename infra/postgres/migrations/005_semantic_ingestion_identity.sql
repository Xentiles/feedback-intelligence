BEGIN;

-- JSON serializers differ in property order, numeric spelling and UTC suffix.
-- Compare the actual stored content rather than rewriting historical fingerprints.
CREATE OR REPLACE FUNCTION feedback.normalized_record_content(content jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog AS $$
DECLARE
    result jsonb := content;
    field text;
BEGIN
    result := jsonb_set(result, '{occurred_at}',
        to_jsonb((content->>'occurred_at')::timestamptz AT TIME ZONE 'UTC'));
    FOREACH field IN ARRAY ARRAY['purchased_at', 'delivered_at', 'expected_delivery_at']
    LOOP
        IF content->'operational_context'->>field IS NOT NULL THEN
            result := jsonb_set(result, ARRAY['operational_context', field],
                to_jsonb((content->'operational_context'->>field)::timestamptz
                    AT TIME ZONE 'UTC'));
        END IF;
    END LOOP;
    RETURN result;
END
$$;

CREATE OR REPLACE FUNCTION feedback.record_content_matches(record_id uuid, content jsonb)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = pg_catalog AS $$
    SELECT feedback.normalized_record_content(jsonb_build_object(
        'schema_version', record.schema_version,
        'feedback_id', record.feedback_id,
        'source', jsonb_build_object(
            'provider_id', record.source_provider_id,
            'dataset_name', record.source_dataset_name,
            'dataset_version', record.source_dataset_version,
            'source_record_id', record.source_record_id),
        'original_text', restricted.original_text,
        'title', restricted.title,
        'occurred_at', record.occurred_at,
        'rating', record.rating,
        'related_products', record.related_products,
        'order_id', record.order_id,
        'channel', record.channel,
        'language', record.language,
        'metadata', record.metadata,
        'operational_context', record.operational_context,
        'privacy_status', restricted.privacy_status
    )) = feedback.normalized_record_content(content)
    FROM feedback.feedback_records AS record
    JOIN feedback.restricted_feedback_text AS restricted USING (feedback_id)
    WHERE record.feedback_id = record_id
$$;

REVOKE ALL ON FUNCTION feedback.normalized_record_content(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION feedback.record_content_matches(uuid, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION feedback.normalized_record_content(jsonb),
    feedback.record_content_matches(uuid, jsonb) TO feedback_api, feedback_worker;

INSERT INTO feedback.schema_migrations(version)
VALUES ('005_semantic_ingestion_identity') ON CONFLICT (version) DO NOTHING;
COMMIT;
