# MMS on pharmacy data: training and evaluation

MMS now reads the dbt [replenishment marts](../transform/dbt/models/marts/replenishment/README.md) (`MMS_DATA_SOURCE=mart`). This page records how the stockout-risk model (MB2) was trained, evaluated and improved on the 2023–2025 pharmacy export, and how to reproduce it.

## Problem setup

| Item | Definition |
|---|---|
| Decision date T | Mondays; one snapshot per product from `fct_product_replenishment_snapshot` |
| Cohort | `is_orderable = 1` (sold in 90 days, not consignment, has a dispensary ledger) and dispensary stock > 0 at T |
| Label | Dispensary closing ≤ 0 on any day in (T, T+h], h ∈ {7, 14, 30} |
| Stocktake handling | A product's window is dropped when a stocktake posting falls inside it (per SKU, not per date) |
| Split | Train T ≤ 2024 · validation Jan–May 2025 · test Jun–Dec 2025. Label windows never cross a split boundary |
| Metrics | ROC-AUC, average precision (AP), precision/recall in the daily top 50 (P@50, R@50), lift over prevalence |

Label check: 99.6% of positive windows are explained by sales exceeding the starting dispensary stock. Adjustments and transfers out explain almost none, so the label measures demand-driven stockouts.

Per-date stocktake exclusion, the original MMS behaviour, is unusable on this data. Cycle counts happen on nearly every day, so it would discard every training date.

## Iterations (validation set, h = 14)

| Round | Change | AUC | AP | P@50 |
|---|---|---|---|---|
| 0 | Days-of-supply rule (rank by dispensary cover) | 0.763 | 0.165 | 0.25 |
| 1 | Original MMS HistGB: 4 features, small trees | 0.793 | 0.207 | 0.34 |
| 1 | 20 features from the first mart version | 0.882 | 0.304 | 0.42 |
| 2 | + demand shape, yearly history, transfer and stockout history, product attributes | 0.889 | 0.315 | 0.42 |
| 3 | Daily instead of weekly training rows / deeper trees | no gain (0.878–0.888) | | |
| 3 | Drop stocktake-touched windows from training | 0.889 | 0.328 | 0.42 |
| 4 | Poisson / negative-binomial exceedance probabilities as features | no gain | | |
| 5 | Pruned to 35 numeric features (adopted as `feature_set=mart`) | 0.892 | 0.325 | 0.41 |

The strongest new feature is `dispensary_peak_cover_days`: dispensary stock divided by the 90-day peak daily sale. `days_since_last_stockout`, `sold_qty_max_90d` and `sold_qty_365d` follow. Product category, drug class and manufacturer added less than 0.002 AUC. They were left out so that all MMS features stay numeric.

## Held-out test results (Jun–Dec 2025)

Each model was refit on train + validation and evaluated once on the test period.

| Horizon | Model | AUC | AP | P@50 | R@50 |
|---|---|---|---|---|---|
| 7 d | Days-of-supply rule | 0.788 | 0.174 | 0.27 | 0.18 |
| 7 d | Original MMS HistGB | 0.792 | 0.166 | 0.24 | 0.18 |
| 7 d | **Mart HistGB** | **0.887** | **0.246** | **0.32** | **0.23** |
| 14 d | Days-of-supply rule | 0.760 | 0.232 | 0.34 | 0.12 |
| 14 d | Original MMS HistGB | 0.768 | 0.234 | 0.36 | 0.14 |
| 14 d | **Mart HistGB** | **0.848** | **0.312** | **0.42** | **0.16** |
| 30 d | Days-of-supply rule | 0.720 | 0.315 | 0.43 | 0.08 |
| 30 d | Original MMS HistGB | 0.736 | 0.342 | 0.53 | 0.11 |
| 30 d | **Mart HistGB** | **0.805** | **0.418** | **0.58** | **0.12** |

The MMS-native backtest gives the same picture: CLI training on 111 Mondays (185,508 rows, 6.5% positive) and `inventory-mms backtest` over 29 test Mondays at h = 14, K = 50.

| Artifact | ROC-AUC | Precision@50 | Recall@50 | Lift |
|---|---|---|---|---|
| `basic` (original 4 features, retrained on pharmacy data) | 0.780 | 0.361 | 0.143 | 5.3 |
| `mart` (35 features) | **0.849** | **0.419** | **0.165** | **6.1** |

Recall@50 is bounded by the cohort: about 140 products per date stock out within 14 days, so a 50-item review list cannot catch most of them. Raise K or shorten the horizon when wider coverage matters.

**Calibration.** Scores are close to observed frequencies above 0.2 but underestimate the low bins. For h = 14 on test, the 0.05–0.1 bin predicts 7% and observes 14%. The 2025 stockout rate (8.0%) is higher than the training rate (7.4%). The manifest therefore keeps `calibrated: false`; treat `pstar` as a ranking cut-off, not a probability.

## Demand forecast (MB1)

Over the test cohort, the 14-day sales forecast scores WAPE 0.386 (bias +1%) for MA90 and 0.410 for MA30. A blend of the two scores 0.385, and a HistGB Poisson regressor on the mart features scores 0.376 (bias −5%). The gain does not justify replacing MA90, which remains MB1.

## Reproduce

Requires the marts built by `inventory-dw-dss transform`.

```bash
export MMS_DATA_SOURCE=mart
uv run --locked --extra mms inventory-mms train-histgb --feature-set mart --horizon 14 \
  --data-kind verified --artifact-version pharmacy-mart-h14-v1 --output artifacts/pharmacy-mart-h14-v1 \
  --dates 2023-04-03,2023-04-10,...,2025-05-12
MMS_ARTIFACT_PATH=artifacts/pharmacy-mart-h14-v1/histgb.joblib \
MMS_MANIFEST_PATH=artifacts/pharmacy-mart-h14-v1/manifest.json \
uv run --locked --extra mms inventory-mms backtest --horizon 14 --top-k 50 --dates 2025-06-02,...,2025-12-15
```

Training takes about one minute. The last training date plus the horizon must precede the first evaluated date; the artifact's `supervised_data_cutoff` enforces this.

## Known limits and next levers

- Recorded sales censor demand during stockouts, so forecasts for frequently empty products are biased low.
- Most remaining errors are sudden demand spikes on low-stock products. A shorter horizon (7 d) or a larger K catches more of them.
- Flags `dispensary_out_of_stock` and `transfer_from_storeroom` separate incidents in progress, and cases a storeroom transfer can fix, from purchase decisions. The allocation still proposes purchase quantities only.
- No lead-time or supplier data exists, so the coverage target `tau` remains a manager parameter.
