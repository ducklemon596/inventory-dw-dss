-- DIAGNOSTIC: Observed ledger gaps; these values are not movement measures
-- No reproducible approved stocktake-batch algorithm was supplied. Labels below
-- describe only adjacent descriptions; they do not assert batch cancellation.
with preceding_segments as (
    select
        *,
        lagInFrame(toNullable(segment_id)) over (
            partition by dataset_name, product_id, warehouse_id order by dataset_row_number
            rows between unbounded preceding and current row
        ) as previous_segment_id
    from {{ ref('int_inventory_segments') }}
)
select
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
    closing_stock_unit_id as stock_unit_id,
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
        and positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
        'BOTH_ADJACENT_DESCRIPTIONS_MENTION_STOCKTAKE',
        positionCaseInsensitiveUTF8(ifNull(previous_transaction_description, ''), 'stokopname') > 0
        or positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
        'ONE_ADJACENT_DESCRIPTION_MENTIONS_STOCKTAKE', 'OTHER_OBSERVED_GAP'
    ) as diagnostic_class,
    'Recorded opening minus preceding source-sequence closing; adjacent description keyword only' as diagnostic_evidence
from preceding_segments
where is_discontinuity = 1
