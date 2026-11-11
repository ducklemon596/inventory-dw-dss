# MMS normalized export contract (mms-v1)

The warehouse currently uses **ClickHouse**, not DuckDB. Its observed balances
cannot be renamed to available stock; absent dates cannot be renamed to zero
sales. MMS therefore consumes a separately verified normalized DuckDB export.
`DuckDBDataProvider` is read-only and never runs dbt, loads data, or publishes marts.
The in-memory provider applies the same validation rules.

## Approval boundary

Before a production export is released, the data owner must establish:

- Pharmacy-wide aggregation across Apotek and Gudang Obat 1, with compatible
  product stock units, current-at-T scope, and no double counting of transfers.
- What available stock means; the current recorded closing balances do not
  establish reservations, allocatable quantity or physical inventory truth.
- Explicit sales coverage for every calendar day in the lookback. The current
  sparse observed marts do not prove zero demand on missing days.
- Approved quantity conversions, a defensible recorded revenue proxy (optional),
  SKU eligibility and stocktaking/SOP202508 exclusions.
- A versioned export with only features observed by T. The existing source has
  no arrival-time history, so this is event-time backtesting, not proof that a
  late correction was historically available. Do not claim stronger availability.

MMS does not currently build this export from ClickHouse automatically. Refusing
an unverified export is deliberate. Existing warehouse facts and UOM rules are
unchanged. See [warehouse semantics](data-semantics.md).

## Required tables

`mms_inventory_daily`: one row per `(analysis_date, sku_id)`, already aggregated
to the verified pharmacy scope. No silent carry-forward of stale stock.

| Column | Type / rule |
| --- | --- |
| analysis_date | DATE, exact requested T |
| sku_id | Nonempty VARCHAR, unique at T |
| available_stock | Finite number; negative values remain visible but cannot order |
| stock_unit | Nonempty product-specific VARCHAR |
| location_scope | Must equal `pharmacy_total` |
| snapshot_version | Nonempty immutable export/snapshot ID, consistent within T |
| data_version | Nonempty dataset/UOM contract version, consistent within T |
| feature_as_of | DATE <= T; producer attests all features use data at/before this date |
| eligible | Explicit BOOLEAN, not inferred from risk score |
| features | JSON object of additional finite numeric features; may not override built-ins |

Optional fields: `days_since_last_receipt` (nonnegative integer), `flags`
(VARCHAR array), `observed_stockout_days`, `diagnostic_observed_days` (nonnegative
counts). Chronic diagnostics require `sop_excluded_diagnostics` in flags and
counts computed after removing SOP days. These diagnostics are not outcome labels.

`mms_sales_daily`: one explicitly verified row per `(sku_id, sales_date)` for
each of the **90 calendar days T-89 through T inclusive**.

| Column | Type / rule |
| --- | --- |
| sku_id | Same product identifier |
| sales_date | DATE |
| quantity | Finite nonnegative recorded quantity in that product's approved stock unit |
| revenue | Finite nonnegative verified revenue proxy, or NULL (not missing-as-zero) |

MMS rejects incomplete coverage, duplicate days, missing stock and future
features. Future sales rows and sales before T-89 do not enter a snapshot.
MA90 = sum(quantity)/90. `dos = max(stock,0)/vel90`, or NULL when vel90=0.
Returns/net demand need their own verified contract; negative sales are rejected.
RevenueAtRisk refuses candidates without a verified revenue proxy.

## Optional historical outcomes

`mms_outcome_metadata`: exactly one row: `data_cutoff DATE`,
`outcome_version VARCHAR`. The cutoff is the last fully available observation
date, never the current clock date.

`mms_outcomes_daily`: one explicit row per `(observation_date, sku_id)`:
`sales_quantity` (nonnegative finite stock units), `stockout BOOLEAN` (verified
pharmacy-level label), `received_quantity` (nonnegative verified receipt quantity),
`sop_day BOOLEAN`. These values are independently observed, never filled from a
feature snapshot or inferred from a negative balance. Dates T+1 through T+horizon
must all be present. Missing or cutoff-short windows are reported as incomplete.
Windows with SOP observations are excluded; the 2025-07-31 30-day decision is
explicitly excluded as `excluded_sop202508`.

## Versions and determinism

Snapshots and rows are frozen; numeric extra feature maps are read-only. SKU ID
is the last sort key in every ranking. Every result includes the exact date,
snapshot/data/artifact versions, policy versions and parameters. Saving a session
stores the original result and manager actions, rather than rerunning it.
Reproduction requires retaining the corresponding export and trusted artifact;
an identifier alone cannot reconstruct deleted data.

Q is a scenario sum of product-specific units, **not money or a common physical
measure** across tablets, bottles and packs. This simplifying resource assumption
must be accepted by the scenario user. It does not estimate purchasing cost.
