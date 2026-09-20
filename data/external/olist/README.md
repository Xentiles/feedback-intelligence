# Olist raw data location

This directory documents the optional **Brazilian E-Commerce Public Dataset by
Olist**, obtained from Kaggle handle `olistbr/brazilian-ecommerce`.

- Dataset license: **CC BY-NC-SA 4.0**
- Source: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>
- Attribution: Olist, *Brazilian E-Commerce Public Dataset*

Feedback Intelligence is not affiliated with Olist. The reference integration is
for non-commercial demonstration and research. The dataset license applies to the
Olist data, not automatically to this repository's source code. Users must obtain
the files from the original source and comply with its license and terms.

Download with:

```sh
cd services/decision-worker
uv run --locked feedback-data fetch olist
```

Or manually place the extracted CSV files in `data/external/olist/raw/`. Everything
inside `raw/` is Git-ignored and excluded from Docker build contexts. Never commit
Kaggle credentials or raw customer data.
