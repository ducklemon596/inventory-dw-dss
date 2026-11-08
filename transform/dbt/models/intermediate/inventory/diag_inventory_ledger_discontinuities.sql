-- DIAGNOSTIC: Observed ledger gaps; these values are not movement measures
-- No reproducible approved stocktake-batch algorithm was supplied. Labels below
-- describe only adjacent descriptions; they do not assert batch cancellation.
WITH preceding_segments AS (
    SELECT
        *,
        lagInFrame(toNullable(segment_id)) OVER (
            PARTITION BY dataset_name, product_id, warehouse_id
            ORDER BY dataset_row_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS previous_segment_id
    FROM {{ ref('int_inventory_segments') }}
)
SELECT
    dataset_name,
    product_id,
    warehouse_id,
    inventory_movement_id,
    previous_movement_id,
    dataset_row_number,
    previous_source_sequence,
    movement_date,
    movement_at,
    previous_movement_at,
    previous_closing_quantity,
    opening_stock_quantity,
    continuity_delta_qty,
    closing_stock_unit_id AS stock_unit_id,
    transaction_type,
    transaction_description,
    previous_transaction_description,
    segment_id,
    previous_segment_id,
    segment_start_sequence,
    segment_end_sequence,
    segment_boundary_reason,
    multiIf(
        positionCaseInsensitiveUTF8(ifNull(previous_transaction_description, ''), 'stokopname') > 0
        AND positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
        'BOTH_ADJACENT_DESCRIPTIONS_MENTION_STOCKTAKE',
        positionCaseInsensitiveUTF8(ifNull(previous_transaction_description, ''), 'stokopname') > 0
        OR positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
        'ONE_ADJACENT_DESCRIPTION_MENTIONS_STOCKTAKE', 'OTHER_OBSERVED_GAP'
    ) AS diagnostic_class,
    'Recorded opening minus preceding source-sequence closing; adjacent description keyword only' AS diagnostic_evidence
FROM preceding_segments
WHERE is_discontinuity = 1
