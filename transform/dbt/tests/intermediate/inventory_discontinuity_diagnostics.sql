-- Gap diagnostics must cover every detected gap once, without becoming movements.
with expected as (
    select inventory_movement_id, previous_movement_id, previous_source_sequence,
           previous_closing_quantity, opening_stock_quantity, continuity_delta_qty, segment_id,
           lagInFrame(toNullable(segment_id)) over (
               partition by dataset_name, product_id, warehouse_id order by dataset_row_number
               rows between unbounded preceding and current row) as expected_previous_segment,
           is_discontinuity,
           multiIf(
               positionCaseInsensitiveUTF8(ifNull(previous_transaction_description, ''), 'stokopname') > 0
               and positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
               'BOTH_ADJACENT_DESCRIPTIONS_MENTION_STOCKTAKE',
               positionCaseInsensitiveUTF8(ifNull(previous_transaction_description, ''), 'stokopname') > 0
               or positionCaseInsensitiveUTF8(ifNull(transaction_description, ''), 'stokopname') > 0,
               'ONE_ADJACENT_DESCRIPTION_MENTIONS_STOCKTAKE', 'OTHER_OBSERVED_GAP') as expected_class
    from {{ ref('int_inventory_segments') }}
)
select coalesce(expected.inventory_movement_id, actual.inventory_movement_id) as inventory_movement_id
from (select * from expected where is_discontinuity) as expected
full outer join {{ ref('diag_inventory_ledger_discontinuities') }} as actual
    on expected.inventory_movement_id = actual.inventory_movement_id
where expected.inventory_movement_id is null or actual.inventory_movement_id is null
    or not isNotDistinctFrom(expected.previous_movement_id, actual.previous_movement_id)
    or not isNotDistinctFrom(expected.previous_source_sequence, actual.previous_source_sequence)
    or not isNotDistinctFrom(expected.continuity_delta_qty, actual.continuity_delta_qty)
    or not isNotDistinctFrom(expected.previous_closing_quantity, actual.previous_closing_quantity)
    or expected.opening_stock_quantity != actual.opening_stock_quantity
    or expected.segment_id != actual.segment_id
    or not isNotDistinctFrom(expected.expected_previous_segment, actual.previous_segment_id)
    or expected.expected_class != actual.diagnostic_class
settings join_use_nulls = 1
