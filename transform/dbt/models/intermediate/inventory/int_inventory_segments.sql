-- SEGMENTS: One movement assigned to one locally anchored continuity segment
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, warehouse_id, dataset_row_number)'
) }}

-- A gap starts a new anchor at its recorded opening; the gap itself is not a receipt or issue.
WITH assigned AS (
    SELECT
        *,
        max(if(is_ledger_start OR is_discontinuity, dataset_row_number, toUInt32(0)))
            OVER ledger AS segment_start_sequence
    FROM {{ ref('int_inventory_ledger_ordered') }}
    WINDOW ledger AS (
        PARTITION BY dataset_name, product_id, warehouse_id
        ORDER BY dataset_row_number
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
),

anchored AS (
    SELECT
        *,
        -- JSON tuple encoding is unambiguous even when dataset names contain separators.
        toJSONString(tuple(dataset_name, product_id, warehouse_id, segment_start_sequence)) AS segment_id,
        max(dataset_row_number) OVER segment AS segment_end_sequence,
        argMin(opening_stock_quantity, dataset_row_number) OVER segment AS segment_opening_quantity,
        argMin(movement_at, dataset_row_number) OVER segment AS segment_started_at,
        argMax(movement_at, dataset_row_number) OVER segment AS segment_ended_at,
        argMin(boundary_reason, dataset_row_number) OVER segment AS segment_boundary_reason,
        sum(toDecimal128(recorded_delta_qty, 6)) OVER running_segment AS segment_cumulative_delta_qty
    FROM assigned
    WINDOW
        -- Segment metadata covers the entire segment, including later observations.
        segment AS (
            PARTITION BY dataset_name, product_id, warehouse_id, segment_start_sequence
            ORDER BY dataset_row_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ),
        running_segment AS (
            PARTITION BY dataset_name, product_id, warehouse_id, segment_start_sequence
            ORDER BY dataset_row_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )
)

SELECT
    *,
    toDecimal128(segment_opening_quantity, 6) + segment_cumulative_delta_qty AS reconstructed_closing_quantity
FROM anchored
