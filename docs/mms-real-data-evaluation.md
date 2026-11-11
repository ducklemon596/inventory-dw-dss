# MMS on pharmacy data: training and evaluation

MMS reads the dbt [replenishment marts](../transform/dbt/models/marts/replenishment/README.md). Metric and term definitions are in the [MMS README](../src/inventory_dw_dss/mms/README.md). This page records how the stockout-risk model (MB2) was trained, evaluated and improved on the 2023–2025 pharmacy export, and how to reproduce it.

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
| 5 | Pruned to 35 numeric features (the current feature set) | 0.892 | 0.325 | 0.41 |

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
| Original 4-feature model, retrained on pharmacy data (since removed) | 0.780 | 0.361 | 0.143 | 5.3 |
| `mart` (35 features) | **0.849** | **0.419** | **0.165** | **6.1** |

Recall@50 is bounded by the cohort: about 140 products per date stock out within 14 days, so a 50-item review list cannot catch most of them. Raise K or shorten the horizon when wider coverage matters.

**Calibration.** Scores are close to observed frequencies above 0.2 but underestimate the low bins. For h = 14 on test, the 0.05–0.1 bin predicts 7% and observes 14%. The 2025 stockout rate (8.0%) is higher than the training rate (7.4%). The manifest therefore keeps `calibrated: false`; treat `pstar` as a ranking cut-off, not a probability.

## Risk target: shelf stockout vs pharmacy shortfall

A review of the top 50 misses on test (h = 14) showed that the recorded-stockout label partly measures past staff actions:

- About 40% of the "false" alerts sold more than their starting dispensary stock but were refilled in time. The risk was real.
- Almost all remaining misses were slow movers with one unit left that did not sell. That is genuine uncertainty, not a logic error.
- Labels, splits and cutoffs were rechecked: the label matches the minimum dispensary balance in 100% of rows, and training labels end before the first test date.

MMS therefore supports two targets. Each artifact declares its target in the manifest (`risk_target`), and backtests label outcomes by the same target:

| Target | Event in (T, T+h] | Rate (test, h = 14) | Use |
|---|---|---|---|
| `dispensary_stockout` | Dispensary balance reaches zero | 8% | Shelf alert; includes how promptly staff transferred stock |
| `pharmacy_shortfall` | Sales reach dispensary + storeroom stock at T | 12.5% | **Purchase decisions** (recommended for order planning) |

`inventory-mms backtest`, 29 test Mondays, K = 50, with each artifact evaluated on its own target:

| Artifact | ROC-AUC | Precision@50 | Recall@50 | Lift |
|---|---|---|---|---|
| `dispensary_stockout` | 0.849 | 0.419 | 0.165 | 6.1 |
| `pharmacy_shortfall` | **0.900** | **0.764** | **0.181** | **6.8** |

The precision figures answer different questions and are not one model beating another. In a cross-check on the same test rows (stocktake windows excluded), the pharmacy-shortfall artifact gives:

- Calibrated scores: predicted 0.07 / 0.25 / 0.59 / 0.81 against observed 0.10 / 0.27 / 0.61 / 0.82.
- Top-50 capture of the at-risk daily revenue: 34%, and 49% when ranked by score × revenue (`RevenueAtRisk`). The shelf artifact captures 7% and 27%.

A training-free negative-binomial probability P(14-day demand ≥ stock), the same distribution as MB3, reaches AUC 0.894 on this target. HistGB adds little there. Its behavioural features matter more for the shelf target.

## Demand forecast (MB1)

Over the test cohort, the 14-day sales forecast scores WAPE 0.386 (bias +1%) for MA90 and 0.410 for MA30. A blend of the two scores 0.385, and a HistGB Poisson regressor on the mart features scores 0.376 (bias −5%). The gain does not justify replacing MA90, which remains MB1.

## Replenishment policy (MB3)

The coverage rule orders `ceil(tau × MA90 − stock)`. Because it targets mean demand, over 16 days (14 + 2 lead time) it covered actual demand in only 61% of test windows. The service-level policy (`policy=service_level`) orders up to a quantile of demand over the review period plus lead time.

Demand distribution, checked on 58,659 test snapshots (16-day windows):

| Method | Target | Covered | Pinball loss |
|---|---|---|---|
| MA90 × days (coverage rule) | mean | 0.61 | — |
| Normal from 90-day mean/std | 0.90 / 0.95 | 0.865 / 0.898 | 3.49 / 2.39 |
| **Negative binomial from 90-day mean/std** | 0.90 / 0.95 | **0.901 / 0.940** | 3.49 / **2.31** |
| Empirical 365-day quantile of 16-day sums | 0.90 / 0.95 | 0.912 / 0.944 | 3.61 / 2.38 |
| HistGB quantile regression (11 features) | 0.90 / 0.95 | 0.880 / 0.932 | 3.40 / 2.20 |

The negative binomial stays calibrated for slow (two thirds of products), medium and fast movers. HistGB undercovers fast movers (0.83 at a 0.90 target) and needs retraining, so it was not adopted.

Policy replay with `inventory-mms simulate-policy` covers 2037 products orderable on 2025-06-02, through 2025-12-28. Orders are reviewed weekly, the lead time is 2 days and demand is recorded sales:

| Policy | Fill rate | Value fill rate | Stockout days | Avg inventory value (M) |
|---|---|---|---|---|
| coverage 14 d | 0.943 | 0.933 | 6.5% | 251 |
| coverage 21 d | 0.977 | 0.971 | 3.3% | 317 |
| coverage 28 d | 0.988 | 0.985 | 2.0% | 389 |
| service 90% | 0.956 | 0.947 | 6.7% | 260 |
| **service 95%** | 0.975 | 0.973 | **2.7%** | **297** |
| **service 98%** | 0.988 | 0.987 | **1.4%** | **343** |
| service ABC (A 98 / B 95 / C 90) | 0.981 | 0.980 | 4.5% | 325 |

The service policy reaches the coverage rule's fill rate with 7–12% less stock and fewer stockout days. It also holds up when lead time grows. From 1 to 4 days, service 95% keeps a 0.975 fill rate, while coverage 21 d falls from 0.981 to 0.968, because the coverage rule ignores lead time. ABC levels raise the value fill rate but leave more C-class stockout days, so they are an option, not the default. Imputing MA90 demand on recorded empty days lowers every fill rate by about 3 points and keeps the ranking.

Only 1.4% of 2025 dispensary-stockout days had storeroom stock. Transfers therefore stay a flag rather than a separate proposal.

Replay limits:
- Supply is complete and on time.
- There are no pack sizes or minimum orders.
- Stock is pharmacy-wide.
- Recorded history (488 M average stock, 12.7% stockout days) ran under different supply conditions and is context only.

## Reproduce

Requires the marts built by `inventory-dw-dss transform`.

```bash
uv run --locked --extra mms inventory-mms train --dates 2023-04-03..2025-05-12 --horizon 14 \
  --target pharmacy_shortfall --version shortfall-h14-v1 --output artifacts/shortfall-h14-v1
export MMS_ARTIFACT_PATH=artifacts/shortfall-h14-v1/histgb.joblib MMS_MANIFEST_PATH=artifacts/shortfall-h14-v1/manifest.json
uv run --locked --extra mms inventory-mms backtest --dates 2025-06-02..2025-12-15 --horizon 14
uv run --locked --extra mms inventory-mms simulate-policy --start 2025-06-02 --end 2025-12-28 \
  --policies coverage:14,coverage:21,coverage:28,service:0.9,service:0.95,service:0.98,service:abc
```

Use `--target dispensary_stockout` for the shelf-alert model. Training takes about one minute and reproduces the pharmacy-shortfall row above (188,249 training rows; AUC 0.900, Precision@50 0.764). The last training date plus the horizon must precede the first evaluated date; the bundle's `supervised_data_cutoff` enforces this.

## Known limits and next levers

- Recorded sales censor demand during stockouts, so forecasts for frequently empty products are biased low.
- Most remaining errors are sudden demand spikes on low-stock products. A shorter horizon (7 d) or a larger K catches more of them.
- Flags `dispensary_empty` and `transfer_from_storeroom` separate incidents in progress, and cases a storeroom transfer can fix, from purchase decisions. The allocation still proposes purchase quantities only.
- No lead-time or supplier data exists, so lead time and review period remain manager parameters.
