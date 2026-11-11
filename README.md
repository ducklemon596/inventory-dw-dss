# Pharmacy inventory DW and DSS

A data warehouse for one pharmacy's sales and stock ledger. On top of it sits a decision-support layer (MMS) that flags products about to run out and proposes how much to order.

```
CSV export ─(optional)─► PostgreSQL OLTP ─► ClickHouse raw ─► dbt: staging → intermediate → marts ─► MMS (CLI + Streamlit)
```

| Part | Guide |
|---|---|
| Load the source CSVs into PostgreSQL | [PostgreSQL loader](src/inventory_dw_dss/oltp_ingestion/README.md) |
| Copy PostgreSQL into ClickHouse raw | [Raw loader](src/inventory_dw_dss/README.md) |
| Build and test the marts | [dbt project](transform/dbt/README.md) |
| Risk model, order policies, metrics, app | [MMS](src/inventory_dw_dss/mms/README.md) |
| What the tables mean | [Data model](docs/data-model.md), [semantics](docs/data-semantics.md), [DSS handover](docs/dss-handover.md) |
| Model results on the pharmacy data | [Evaluation report](docs/mms-real-data-evaluation.md) |

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker and Compose.

```bash
uv sync --locked
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait
```

With PostgreSQL already loaded, refresh the warehouse:

```bash
uv run --locked inventory-dw-dss load raw
uv run --locked inventory-dw-dss transform
```

Then train a risk model and open the planning app. The [MMS README](src/inventory_dw_dss/mms/README.md) has the full set of commands.

```bash
uv run --locked --extra mms inventory-mms train --dates 2023-04-03..2025-05-12 \
  --output artifacts/shortfall-h14-v1 --version shortfall-h14-v1
MMS_ARTIFACT_PATH=artifacts/shortfall-h14-v1/histgb.joblib MMS_MANIFEST_PATH=artifacts/shortfall-h14-v1/manifest.json \
  uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/app.py
```

## Source data

The original exports come from the [Mendeley Data archive (version 2)](https://data.mendeley.com/public-api/zip/w6zjtdjk9m/download/2). Each file exceeds GitHub's size limit, so they are not in Git. Extract the sales and stock files to `data/raw/sales_raw.csv` and `data/raw/stock_raw.csv`, keeping their contents and `RowNumber` values. They are only needed to initialize PostgreSQL.

## Key terms

| Term | Meaning |
|---|---|
| Dispensary / storeroom | The shelf customers buy from (Apotek) / back stock (Gudang Obat 1) |
| Available stock | Dispensary + storeroom at day end. Order quantities are based on it |
| MA90 | Units sold in the last 90 days ÷ 90, the demand forecast |
| Pharmacy shortfall | Sales over the next h days reach the available stock, so the pharmacy runs out without a purchase |
| Service level | Probability that stock covers demand until the next delivery |
| UOM | Unit of measure. Sales lines are converted to the product's stock unit by a governed mapping |

Metric definitions (Precision@K, lift, ROC-AUC, WAPE, fill rate) are in the [MMS README](src/inventory_dw_dss/mms/README.md#metrics).

## Services

[infra](infra/README.md) documents connection settings and volumes. An optional ClickHouse web UI is available:

```bash
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --no-deps ch-ui   # http://localhost:3488
```

## Tests

[tests/README.md](tests/README.md) lists every suite. The quick checks are:

```bash
uv run --locked inventory-dw-dss transform                    # dbt models + data tests
uv run --locked --extra ui --group dev pytest tests/mms       # MMS, no database needed
```
