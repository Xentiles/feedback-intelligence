# Feedback decision evaluation

- Split: `all`
- Reference: `ai_reference` / `gpt-5.6-sol`
- Engine: `llm-openai` / `gpt-5.4-mini-2026-03-17`
- Records: 192
- Target records: 480
- Partial evaluation: `true`
- Successful predictions: 192
- Prediction errors: 0
- Primary-topic macro-F1: 0.7828
- Primary-topic accuracy: 0.8490

| Question | Primitive | Main quality metric | Brier | ECE |
| --- | --- | ---: | ---: | ---: |
| `primary_topic` | choice | macro-F1 0.7828 | 0.0252 | 0.0413 |
| `mentions_product` | noul | F1 0.9289 | 0.0585 | 0.0292 |
| `mentions_delivery` | noul | F1 0.8267 | 0.0512 | 0.0432 |
| `mentions_support` | noul | F1 1.0000 | 0.0014 | 0.0090 |
| `overall_experience` | score | MAE 0.3953 | 0.0829 | 0.0732 |
| `product_experience` | score | MAE 0.2070 | 0.0461 | 0.0583 |
| `delivery_experience` | score | MAE 0.1507 | 0.0407 | 0.0815 |
| `support_experience` | score | MAE 0.0976 | 0.0185 | 0.0639 |
| `reports_product_defect` | noul | F1 0.9254 | 0.0298 | 0.0332 |
| `issue_severity` | score | MAE 0.5951 | 0.1640 | 0.2273 |
| `resolution_status` | choice | macro-F1 0.4413 | 0.1489 | 0.3423 |
| `actionable_feedback` | noul | F1 0.9973 | 0.0153 | 0.0642 |
| `explicit_repurchase_risk` | noul | F1 0.0000 | 0.0000 | 0.0013 |
| `defect_type` | choice | macro-F1 0.4327 | 0.0268 | 0.0882 |

This interim report uses AI-reviewed reference labels and is not human gold. It is generated from 192 completed records in a frozen 480-record sample and one prediction file. The partial subset is not directly equivalent to the complete SemIf and rule runs. Calibration and selective metrics are descriptive and should be interpreted with the reported sample counts.

Owner-reported OpenAI usage for this experiment was 477,777 tokens and `$0.39`.
Linear extrapolation by record count estimates approximately `$0.98` for 480 records. Adapter
execution counters are retained separately in the JSON report and do not replace
the billing observation.
