-- Independent reverse traversal of staging verifies all predecessor associations.
with expected as (
    select
        inventory_movement_id,
        leadInFrame(toNullable(inventory_movement_id)) over reverse_ledger as expected_id,
        leadInFrame(toNullable(dataset_row_number)) over reverse_ledger as expected_sequence,
        leadInFrame(toNullable(closing_stock_quantity)) over reverse_ledger as expected_closing,
        leadInFrame(toNullable(closing_stock_unit_id)) over reverse_ledger as expected_unit,
        leadInFrame(toNullable(movement_at)) over reverse_ledger as expected_at,
        leadInFrame(transaction_description) over reverse_ledger as expected_description
    from {{ ref('stg_inventory_movements') }}
    window reverse_ledger as (
        partition by dataset_name, product_id, warehouse_id order by dataset_row_number desc
        rows between unbounded preceding and unbounded following
    )
)
select actual.inventory_movement_id
from {{ ref('int_inventory_ledger_ordered') }} as actual
inner join expected on actual.inventory_movement_id = expected.inventory_movement_id
where not isNotDistinctFrom(actual.previous_movement_id, expected.expected_id)
    or not isNotDistinctFrom(actual.previous_source_sequence, expected.expected_sequence)
    or not isNotDistinctFrom(actual.previous_closing_quantity, expected.expected_closing)
    or not isNotDistinctFrom(actual.previous_closing_unit_id, expected.expected_unit)
    or not isNotDistinctFrom(actual.previous_movement_at, expected.expected_at)
    or not isNotDistinctFrom(actual.previous_transaction_description, expected.expected_description)
    or actual.is_ledger_start != isNull(expected.expected_sequence)
    or actual.is_discontinuity != ifNull(actual.opening_stock_quantity != expected.expected_closing, false)
    or actual.is_continuous != ifNull(actual.opening_stock_quantity = expected.expected_closing, false)
    or not isNotDistinctFrom(actual.continuity_delta_qty, actual.opening_stock_quantity - expected.expected_closing)
    or ifNull(actual.previous_source_sequence >= actual.dataset_row_number, false)
    or ifNull(actual.previous_movement_at > actual.movement_at, false)
