-- Dense daily position per product ledger, from its first movement to the export end date.
-- Ledger rule: a balance holds until the next movement, so days without movements carry the
-- last closing forward and have zero flows. Continuity is 99.98% in the source ledger;
-- the remaining gaps are exposed as balance_gap_qty on the day they occur.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, warehouse_id, position_date)'
) }}

WITH daily AS (
    SELECT
        * REPLACE (
            -- Nullable keys make unmatched calendar days NULL regardless of join_use_nulls.
            toNullable(closing_stock_quantity) AS closing_stock_quantity,
            toNullable(stock_unit_id) AS stock_unit_id
        )
    FROM {{ ref('int_inventory_daily_flows') }}
),

-- The export end is shared by all ledgers; a quiet product is still observed until then.
dataset_bounds AS (
    SELECT
        dataset_name,
        max(position_date) AS last_date
    FROM daily
    GROUP BY dataset_name
),

ledger_bounds AS (
    SELECT
        dataset_name,
        product_id,
        warehouse_id,
        min(position_date) AS first_date
    FROM daily
    GROUP BY
        dataset_name,
        product_id,
        warehouse_id
),

calendar AS (
    SELECT
        ledger_bounds.dataset_name AS dataset_name,
        ledger_bounds.product_id AS product_id,
        ledger_bounds.warehouse_id AS warehouse_id,
        toDate32(addDays(ledger_bounds.first_date, day_offset)) AS position_date
    FROM ledger_bounds
    INNER JOIN dataset_bounds
        ON ledger_bounds.dataset_name = dataset_bounds.dataset_name
    ARRAY JOIN range(toUInt32(dateDiff('day', ledger_bounds.first_date, dataset_bounds.last_date) + 1)) AS day_offset
),

joined AS (
    SELECT
        calendar.dataset_name AS dataset_name,
        calendar.product_id AS product_id,
        calendar.warehouse_id AS warehouse_id,
        calendar.position_date AS position_date,
        daily.closing_stock_quantity AS observed_closing_quantity,
        daily.stock_unit_id AS observed_stock_unit_id,
        daily.consignment_status AS observed_consignment_status,
        ifNull(daily.sold_qty, 0) AS sold_qty,
        ifNull(daily.customer_return_qty, 0) AS customer_return_qty,
        ifNull(daily.purchase_received_qty, 0) AS purchase_received_qty,
        ifNull(daily.transfer_in_qty, 0) AS transfer_in_qty,
        ifNull(daily.transfer_out_qty, 0) AS transfer_out_qty,
        ifNull(daily.adjustment_qty, 0) AS adjustment_qty,
        ifNull(daily.balance_gap_qty, 0) AS balance_gap_qty,
        ifNull(daily.has_purchase_receipt, 0) AS has_purchase_receipt,
        ifNull(daily.has_stocktake, 0) AS has_stocktake,
        ifNull(daily.movement_count, 0) AS movement_count
    FROM calendar
    LEFT JOIN daily
        ON calendar.dataset_name = daily.dataset_name
        AND calendar.product_id = daily.product_id
        AND calendar.warehouse_id = daily.warehouse_id
        AND calendar.position_date = daily.position_date
)

SELECT
    dataset_name,
    product_id,
    warehouse_id,
    position_date,

    -- anyLast skips NULLs, which carries the latest observed value forward.
    assumeNotNull(anyLast(observed_closing_quantity) OVER ledger_to_date) AS on_hand_qty,
    assumeNotNull(anyLast(observed_stock_unit_id) OVER ledger_to_date) AS stock_unit_id,
    anyLast(observed_consignment_status) OVER ledger_to_date AS consignment_status,
    sold_qty,
    customer_return_qty,
    purchase_received_qty,
    transfer_in_qty,
    transfer_out_qty,
    adjustment_qty,
    balance_gap_qty,
    toUInt8(has_purchase_receipt) AS has_purchase_receipt,
    toUInt8(has_stocktake) AS has_stocktake,
    toUInt32(movement_count) AS movement_count,
    toUInt8(movement_count > 0) AS has_movement
FROM joined
WINDOW ledger_to_date AS (
    PARTITION BY dataset_name, product_id, warehouse_id
    ORDER BY position_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
