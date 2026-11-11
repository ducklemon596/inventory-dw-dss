# Replenishment facts

Two full-rebuild MergeTree tables are the DSS input for demand forecasting, stockout-risk scoring, order-quantity rules and backtesting. [_replenishment.yml](_replenishment.yml) is the field/type/test reference; [Replenishment Intermediate](../../intermediate/replenishment/README.md) owns the dense ledger position.

## Business rules

| Decision | Rule chosen | Reason |
|---|---|---|
| Where stockout is measured | Dispensary (`replenishment_dispensary_warehouse_id`, default Apotek = 1) | Only the dispensary sells; storeroom stock (Gudang Obat 1) prevents lost sales only after a transfer |
| Stockout | Dispensary closing ≤ 0 | Negative balances mean sales were posted before a receipt; the shelf was empty at that point |
| Available stock | Dispensary + storeroom, floored at 0 | What the pharmacy could sell after an internal transfer |
| Demand | Ledger SALE issues in the stock unit | Comparable with balances; sales-line units can differ |
| Sales value | Sum of line `subtotal_amount` | Invoice-level fees and discounts have no verified line allocation |
| Scope | Products with an inventory ledger | 19 sold products have none (mainly blood-test services, about 0.6% of sales value) and cannot be stocked |
| Order cohort | `is_orderable`: sold in 90 days, not consignment, has a dispensary ledger | Consignment stock is replenished by its owner |
| Stocktakes | Flagged per day and per label window | Mass corrections (Jul 2023, Aug 2025) are real stock changes but distort evaluation |

## fct_product_daily_position

[SQL](fct_product_daily_position.sql) aggregates `int_inventory_daily_position` to dataset × product × date. A warehouse contributes zero before its first movement. Columns cover the dispensary/storeroom/pharmacy balances, daily flows (sold, returned, purchased, transferred to the dispensary, adjusted, gap), sales amount and lines from `fct_sales_line`, and status flags for stockout, negative balance, receipt and stocktake.

For example, a product with 3 units in the dispensary and 40 in the storeroom is not a dispensary stockout. If the dispensary falls to 0 while 40 remain in storage, `is_dispensary_stockout = 1` and `is_pharmacy_stockout = 0`: the right action is a transfer, not a purchase.

## fct_product_replenishment_snapshot

[SQL](fct_product_replenishment_snapshot.sql) has the same grain, with `snapshot_date` as decision date T. Because positions are dense, `ROWS` frames equal calendar days.

| Group | Columns | Window |
|---|---|---|
| Position | dispensary/storeroom/pharmacy on hand, `available_qty` | End of T |
| Demand | `sold_qty_7d/30d/90d`, `sale_days_90d`, `avg_daily_sold_qty_90d` (MA90), `sales_amount_90d`, `unit_sales_value_90d` | Days ≤ T |
| Coverage | `pharmacy_days_of_supply`, `dispensary_days_of_supply` | Days ≤ T |
| Service history | days since last sale/receipt, receipt days, transfers, stockout days, stocktake flag, `history_days` | Days ≤ T |
| Eligibility | `is_active_90d`, `has_full_history`, `is_orderable`, `abc_class` (A/B/C by 90-day sales value: 80/15/5% of the day's total) | Days ≤ T |
| Demand shape | `sold_qty_std_90d`, `sold_qty_max_90d`, `demand_cv_90d`, `demand_trend_7_90`, `dispensary_peak_cover_days`, `sold_qty_365d`, `sale_days_365d` | Days ≤ T |
| Refill rhythm | `purchase_receipt_days_365d`, `avg_purchase_receipt_qty_365d`, `transfer_days_90d`, `days_since_last_transfer`, `dispensary_avg/min_on_hand_30d`, `days_since_last_stockout`, `dispensary_stockout_days_365d` | Days ≤ T |
| Labels | `label_dispensary_stockout_{7,14,30}d`, `label_pharmacy_shortfall_{h}d` (sales reach `available_qty`), `label_sold_qty_{h}d`, `label_window_has_stocktake_{h}d` | Days in (T, T+h] |

The demand-shape and refill-rhythm groups were added after backtests showed they lift stockout ranking (`dispensary_peak_cover_days` is the strongest single predictor); see [MMS real-data evaluation](../../../../../docs/mms-real-data-evaluation.md). MMS reads this table directly with `MMS_DATA_SOURCE=mart`.

`label_pharmacy_shortfall_{h}d` is the purchase-risk target. It is independent of how quickly staff refilled the shelf, which the dispensary label also captures. Labels are NULL when T+h passes the export end, so incomplete windows cannot enter training as negatives. Features never read past T.

Typical consumer filters for a risk model at horizon h:

```sql
SELECT *
FROM fct_product_replenishment_snapshot
WHERE is_orderable = 1
  AND dispensary_on_hand_qty > 0          -- incident stockouts only
  AND label_dispensary_stockout_14d IS NOT NULL
  AND label_window_has_stocktake_14d = 0  -- optional for evaluation
```

Over 2024–2025 Monday snapshots this cohort has about 1,850 products per date, with positive rates of 3.9%, 7.5% and 14.4% for 7, 14 and 30 days.

## Run and modify

```bash
uv run --locked inventory-dw-dss transform --select +fct_product_replenishment_snapshot
```

[Position reconciliation](../../../tests/marts/replenishment_position_reconciliation.sql) checks warehouse aggregation and that no sales day of a stock-tracked product is lost. [Window recomputation](../../../tests/marts/replenishment_snapshot_windows.sql) rebuilds features and 30-day labels by date arithmetic for month-start snapshots. A native fixture checks label direction and NULL labels at the export end. Add a horizon by extending `horizons` in the SQL and the YAML columns together.
