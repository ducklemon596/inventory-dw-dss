-- LEDGER: One source movement, ordered within its export / product / warehouse
-- Export sequence is vintage-specific, not a source-native transaction clock.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, warehouse_id, dataset_row_number)'
) }}

-- Source row order determines the predecessor when event timestamps tie.
WITH predecessors AS (
    SELECT
        *,
        lagInFrame(toNullable(inventory_movement_id)) OVER ledger AS previous_movement_id,
        lagInFrame(toNullable(dataset_row_number)) OVER ledger AS previous_source_sequence,
        lagInFrame(toNullable(movement_at)) OVER ledger AS previous_movement_at,
        lagInFrame(toNullable(closing_stock_quantity)) OVER ledger AS previous_closing_quantity,
        lagInFrame(toNullable(closing_stock_unit_id)) OVER ledger AS previous_closing_unit_id,
        lagInFrame(transaction_description) OVER ledger AS previous_transaction_description
    FROM {{ ref('int_inventory_movements_enriched') }}
    WINDOW ledger AS (
        PARTITION BY dataset_name, product_id, warehouse_id
        ORDER BY dataset_row_number
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
),

continuity AS (
    SELECT
        *,
        opening_stock_quantity - previous_closing_quantity AS continuity_delta_qty,
        isNull(previous_source_sequence) AS is_ledger_start,
        toUInt8(ifNull(opening_stock_quantity != previous_closing_quantity, FALSE)) AS is_discontinuity,
        toUInt8(ifNull(opening_stock_quantity = previous_closing_quantity, FALSE)) AS is_continuous
    FROM predecessors
)

SELECT
    *,
    multiIf(
        is_ledger_start, 'LEDGER_START',
        is_discontinuity, 'OPENING_DIFFERS_FROM_PREVIOUS_CLOSING',
        'CONTINUOUS'
    ) AS boundary_reason
FROM continuity
