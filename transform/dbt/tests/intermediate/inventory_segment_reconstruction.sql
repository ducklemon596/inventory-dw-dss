-- Validate within-segment cumulative flow, exact recorded closing, and boundary metadata.
with expected as (
    select
        inventory_movement_id,
        sum(toDecimal128(received_quantity, 6) - toDecimal128(issued_quantity, 6)) over (
            partition by dataset_name, product_id, warehouse_id, segment_start_sequence
            order by dataset_row_number rows between unbounded preceding and current row
        ) as expected_delta
    from {{ ref('int_inventory_segments') }}
)
select actual.inventory_movement_id
from {{ ref('int_inventory_segments') }} as actual
inner join expected on actual.inventory_movement_id = expected.inventory_movement_id
where actual.segment_cumulative_delta_qty != expected.expected_delta
    or actual.reconstructed_closing_quantity != toDecimal128(actual.segment_opening_quantity, 6) + expected.expected_delta
    or actual.reconstructed_closing_quantity != actual.closing_stock_quantity
    or actual.segment_start_sequence > actual.dataset_row_number
    or (actual.is_ledger_start or actual.is_discontinuity) != (actual.segment_start_sequence = actual.dataset_row_number)
    or actual.boundary_reason != multiIf(actual.is_ledger_start, 'LEDGER_START', actual.is_discontinuity,
                                        'OPENING_DIFFERS_FROM_PREVIOUS_CLOSING', 'CONTINUOUS')
