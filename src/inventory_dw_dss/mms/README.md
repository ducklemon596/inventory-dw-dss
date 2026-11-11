# MMS: replenishment decision support

MMS reads the [replenishment marts](../../../transform/dbt/models/marts/replenishment/README.md) in ClickHouse. For an analysis date it lists the products most likely to run out, proposes order quantities and records the manager's decisions.

```
snapshot (mart) ─► risk score (MB2) ─► review list (pstar, ranking, top K) ─► order quantity (MB3) ─► unit budget (MB4) ─► manager decision
```

## Models

| ID | What it answers | How |
|---|---|---|
| MB1 | Expected daily demand | MA90: units sold in the last 90 days ÷ 90 |
| MB2 | Which products will run out | HistGradientBoosting on 35 mart features ([risk.py](models/risk.py)) |
| MB3 | How much to order | Coverage rule or service-level policy ([policy.py](models/policy.py)) |
| MB4 | Which lines get the budget | Rank by profile, allocate units greedily in rank order ([scenario.py](models/scenario.py)) |

**Risk target.** Each model bundle predicts one event within its horizon h (7, 14 or 30 days). The bundle's manifest records which one.

- `pharmacy_shortfall` is the default. It means sales over the next h days reach all stock at T (dispensary + storeroom), so the pharmacy runs out unless it buys. Use it for order planning.
- `dispensary_stockout` means the shelf balance reaches zero. This label also reflects how quickly staff refilled the shelf, so it partly measures past actions rather than risk.

**Order policies.**

- `coverage` orders `ceil(coverage_days × MA90 − available stock)`. It targets average demand, so it is short whenever demand runs above average (about 40% of 16-day windows on 2025 data). It ignores lead time.
- `service_level` orders up to S, the `service_level` quantile of demand over the review period plus the lead time. Demand follows a negative binomial fitted to the 90-day mean and standard deviation. S minus mean demand is the safety stock, so erratic products carry more buffer. With `abc_service`, levels are A 98%, B 95% and C 90%.

**Ranking profiles.**

- `RiskFirst` ranks by highest risk score.
- `RevenueAtRisk` ranks by risk × 90-day revenue.
- `DaysOfSupply` ranks by fewest days of stock.

## Business terms

| Term | Meaning |
|---|---|
| Dispensary / storeroom | The shelf customers buy from / back stock, refilled into the dispensary by transfer |
| Available stock | Dispensary + storeroom at the end of the day, floored at 0 |
| Days of supply | Available stock ÷ MA90 demand |
| Orderable | Sold in the last 90 days, not consignment, stocked at the dispensary |
| Review period | Days between order reviews (weekly = 7) |
| Lead time | Days from ordering to receipt |
| Service level | Probability that stock covers demand until the next delivery |
| Safety stock | Stock above mean demand that absorbs variability |
| ABC class | A = products making up the first 80% of 90-day sales value, B = next 15%, C = rest |
| pstar | Minimum risk score for the review list |
| Unit budget | Total units the plan may allocate. Units of different products are summed as counts, not money |
| Stocktake | A stock count that corrects the balance. Windows containing one are left out of training and evaluation |

## Metrics

| Metric | Meaning |
|---|---|
| Precision@K | Share of the top K products by risk that had the event. "Of 50 alerts, how many were right" |
| Recall@K | Share of all events caught in the top K |
| Lift | Precision@K ÷ event rate. How much better than picking at random |
| ROC-AUC | Chance a random event product scores above a random non-event product (0.5 = random) |
| WAPE | Σ\|forecast − actual\| ÷ Σ actual demand over the horizon (MA90 forecast) |
| Bias | Σ(forecast − actual) ÷ Σ actual. Positive means over-forecast |
| Review coverage | Share of events that the plan's review list contains, after pstar and ranking |
| Fill rate | Units sold ÷ units demanded in a policy replay (lost sales lower it) |
| Value fill rate | Fill rate weighted by unit sales value |
| Stockout day share | Product-days with no stock ÷ product-days with demand |

Scores are not calibrated probabilities. Use them to rank and use pstar as a cut-off. Results on the 2023–2025 pharmacy data are in the [evaluation report](../../../docs/mms-real-data-evaluation.md).

## Run

Requires the marts (`uv run --locked inventory-dw-dss transform`).

```bash
# Train on weekly decision dates; labels must end before the dates you evaluate.
uv run --locked --extra mms inventory-mms train --dates 2023-04-03..2025-05-12 \
  --output artifacts/shortfall-h14-v1 --version shortfall-h14-v1 --horizon 14 --target pharmacy_shortfall

export MMS_ARTIFACT_PATH=artifacts/shortfall-h14-v1/histgb.joblib
export MMS_MANIFEST_PATH=artifacts/shortfall-h14-v1/manifest.json

uv run --locked --extra mms inventory-mms backtest --dates 2025-06-02..2025-12-15 --horizon 14
uv run --locked --extra mms inventory-mms simulate-policy --start 2025-06-02 --end 2025-12-28
uv run --locked --extra mms inventory-mms plan --date 2025-12-01 --service-level 0.95
uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/app.py
```

All commands print JSON. `--dates` takes a comma list or a weekly range `START..END` (Mondays).

| Variable | Default | Purpose |
|---|---|---|
| `MMS_ARTIFACT_PATH`, `MMS_MANIFEST_PATH` | required | Trained model bundle. Only load bundles you trained, because joblib runs code on load |
| `MMS_DECISIONS_PATH` | `reports/mms-decisions.sqlite` | Saved decisions (app) |
| `CLICKHOUSE_HOST`, `_HTTP_PORT`, `_DB`, `_USER`, `_PASSWORD`, `_SECURE` | `localhost`, `8123`, `inventory_dw`, `dbt`, `dbt_local`, `false` | Warehouse connection |

A bundle refuses to score in two cases:
- The mart was rebuilt from another export.
- The analysis date falls before its `supervised_data_cutoff`, because the model already saw those outcomes.

## App

The app has three tabs:

- **Đề xuất** shows the plan as one table. The manager sets Duyệt/Bỏ qua per line, edits the approved quantity, adds a note and saves.
- **So sánh** shows plans A and B on the same snapshot and scores: totals and per-product allocation differences.
- **Lịch sử** shows saved sessions with their decisions.

Changing a setting marks the plan as stale until it is rerun. Saving records a decision, not a purchase order.

## Code map

| File | Role |
|---|---|
| [schemas.py](schemas.py) | Row, snapshot, configuration and plan contracts |
| [data.py](data.py) | ClickHouse mart reader and outcome windows |
| [models/](models) | Risk model, targets, order policies, plan building |
| [training.py](training.py) | Training rows and bundle writing |
| [evaluation/](evaluation) | Backtest metrics and policy replay |
| [service.py](service.py) | Snapshot → scores → plans, shared by CLI and app |
| [decisions.py](decisions.py) | SQLite decision store |
| [cli.py](cli.py), [app.py](app.py) | Command line and Streamlit app |

Tests: `uv run --locked --extra ui --group dev pytest tests/mms` uses in-memory [fixtures](../../../tests/mms/fixtures.py) and needs no database.
