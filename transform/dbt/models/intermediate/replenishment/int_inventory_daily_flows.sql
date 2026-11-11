-- Ledger quantities share the product's stock unit, so flow roles can be summed per day.
-- Roles follow the recorded transaction type; descriptions only identify stocktake postings.

WITH movements AS (
    SELECT
        dataset_name,
        product_id,
        warehouse_id,
        movement_date,
        dataset_row_number,
        transaction_type,
        transaction_description,
        consignment_status,
        opening_stock_quantity,
        received_quantity,
        issued_quantity,
        closing_stock_quantity,
        closing_stock_unit_id,
        is_discontinuity,
        continuity_delta_qty
    FROM {{ ref('int_inventory_segments') }}
),

classified AS (
    SELECT
        *,
        -- Older stocktakes were posted as UNKNOWN rows whose description names the stokopname run.
        toUInt8(
            ifNull(transaction_type = 'IMPORT_STOCKTAKE', FALSE)
            OR positionCaseInsensitive(ifNull(transaction_description, ''), 'stokopname') > 0
        ) AS is_stocktake
    FROM movements
)

SELECT
    dataset_name,
    product_id,
    warehouse_id,
    movement_date AS position_date,

    -- Day boundaries follow source order, consistent with fct_inventory_daily_observed.
    argMin(opening_stock_quantity, dataset_row_number) AS opening_stock_quantity,
    argMax(closing_stock_quantity, dataset_row_number) AS closing_stock_quantity,
    argMax(closing_stock_unit_id, dataset_row_number) AS stock_unit_id,
    argMax(consignment_status, dataset_row_number) AS consignment_status,

    -- Net quantities per role; supplier returns reduce purchases, sale reversals reduce sales.
    sumIf(issued_quantity - received_quantity, transaction_type = 'SALE') AS sold_qty,
    sumIf(received_quantity - issued_quantity, transaction_type = 'RETURN') AS customer_return_qty,
    sumIf(received_quantity - issued_quantity, transaction_type = 'PURCHASE') AS purchase_received_qty,
    sumIf(received_quantity, transaction_type = 'TRANSFER') AS transfer_in_qty,
    sumIf(issued_quantity, transaction_type = 'TRANSFER') AS transfer_out_qty,
    sumIf(
        received_quantity - issued_quantity,
        ifNull(transaction_type NOT IN ('SALE', 'RETURN', 'PURCHASE', 'TRANSFER'), TRUE)
    ) AS adjustment_qty,

    -- Opening-vs-previous-closing gaps are balance corrections, not flows.
    sumIf(assumeNotNull(continuity_delta_qty), is_discontinuity = 1) AS balance_gap_qty,
    sumIf(received_quantity, transaction_type = 'PURCHASE') > 0 AS has_purchase_receipt,
    max(is_stocktake) AS has_stocktake,
    toUInt32(count()) AS movement_count
FROM classified
GROUP BY
    dataset_name,
    product_id,
    warehouse_id,
    movement_date
