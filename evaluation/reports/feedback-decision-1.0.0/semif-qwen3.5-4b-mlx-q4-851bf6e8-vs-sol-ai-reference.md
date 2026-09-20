# Feedback decision evaluation

- Split: `all`
- Reference: `ai_reference` / `gpt-5.6-sol`
- Engine: `semif` / `semif-qwen3.5-4b-mlx-q4-851bf6e8`
- Records: 480
- Target records: 480
- Partial evaluation: `false`
- Successful predictions: 480
- Prediction errors: 0
- Primary-topic macro-F1: 0.8333
- Primary-topic accuracy: 0.8812

| Question | Primitive | Main quality metric | Brier | ECE |
| --- | --- | ---: | ---: | ---: |
| `primary_topic` | choice | macro-F1 0.8333 | 0.0164 | 0.0374 |
| `mentions_product` | noul | F1 0.8705 | 0.1094 | 0.0467 |
| `mentions_delivery` | noul | F1 0.7565 | 0.0670 | 0.0521 |
| `mentions_support` | noul | F1 0.9208 | 0.0302 | 0.0270 |
| `overall_experience` | score | MAE 0.3920 | 0.0963 | 0.1679 |
| `product_experience` | score | MAE 0.4425 | 0.1127 | 0.1787 |
| `delivery_experience` | score | MAE 0.2847 | 0.0783 | 0.0687 |
| `support_experience` | score | MAE 0.3124 | 0.0676 | 0.1459 |
| `reports_product_defect` | noul | F1 0.4762 | 0.1869 | 0.1752 |
| `issue_severity` | score | MAE 0.3890 | 0.1278 | 0.1870 |
| `resolution_status` | choice | macro-F1 0.3523 | 0.1249 | 0.2554 |
| `actionable_feedback` | noul | F1 0.9750 | 0.0299 | 0.0230 |
| `explicit_repurchase_risk` | noul | F1 0.0000 | 0.0080 | 0.0697 |
| `defect_type` | choice | macro-F1 0.4938 | 0.0208 | 0.0872 |

This interim report uses AI-reviewed reference labels and is not human gold. It is generated from a frozen split and one prediction file. Prediction failures stay in the denominator. Calibration and selective metrics are descriptive and should be interpreted with the reported sample counts.
