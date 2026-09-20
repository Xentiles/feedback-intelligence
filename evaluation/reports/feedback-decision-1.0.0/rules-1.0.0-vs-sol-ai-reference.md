# Feedback decision evaluation

- Split: `all`
- Reference: `ai_reference` / `gpt-5.6-sol`
- Engine: `rules` / `rules-1.0.0`
- Records: 480
- Target records: 480
- Partial evaluation: `false`
- Successful predictions: 480
- Prediction errors: 0
- Primary-topic macro-F1: 0.9988
- Primary-topic accuracy: 0.9979

| Question | Primitive | Main quality metric | Brier | ECE |
| --- | --- | ---: | ---: | ---: |
| `primary_topic` | choice | macro-F1 0.9988 | 0.0046 | 0.1808 |
| `mentions_product` | noul | F1 0.9781 | 0.0300 | 0.0750 |
| `mentions_delivery` | noul | F1 0.9017 | 0.0383 | 0.0646 |
| `mentions_support` | noul | F1 1.0000 | 0.0100 | 0.1000 |
| `overall_experience` | score | MAE 0.1146 | 0.0219 | 0.1604 |
| `product_experience` | score | MAE 0.0125 | 0.0137 | 0.1875 |
| `delivery_experience` | score | MAE 0.0167 | 0.0150 | 0.1833 |
| `support_experience` | score | MAE 0.1125 | 0.0212 | 0.1625 |
| `reports_product_defect` | noul | F1 0.9037 | 0.0317 | 0.0729 |
| `issue_severity` | score | MAE 0.1229 | 0.0370 | 0.1354 |
| `resolution_status` | choice | macro-F1 0.6984 | 0.0465 | 0.0929 |
| `actionable_feedback` | noul | F1 1.0000 | 0.0100 | 0.1000 |
| `explicit_repurchase_risk` | noul | F1 0.0000 | 0.0100 | 0.1000 |
| `defect_type` | choice | macro-F1 0.4605 | 0.0167 | 0.2855 |

This interim report uses AI-reviewed reference labels and is not human gold. It is generated from a frozen split and one prediction file. Prediction failures stay in the denominator. Calibration and selective metrics are descriptive and should be interpreted with the reported sample counts.
