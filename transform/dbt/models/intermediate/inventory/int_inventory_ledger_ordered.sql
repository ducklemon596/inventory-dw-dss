-- LEDGER: One source movement, ordered within its export / product / warehouse
-- Export sequence is vintage-specific, not a source-native transaction clock.
{{ config(materialized='table', engine='MergeTree()',
          order_by='(dataset_name, product_id, warehouse_id, dataset_row_number)') }}

with predecessors as (
    select
        *,
        lagInFrame(toNullable(inventory_movement_id)) over ledger as previous_movement_id,
        lagInFrame(toNullable(dataset_row_number)) over ledger as previous_source_sequence,
        lagInFrame(toNullable(movement_at)) over ledger as previous_movement_at,
        lagInFrame(toNullable(closing_stock_quantity)) over ledger as previous_closing_quantity,
        lagInFrame(toNullable(closing_stock_unit_id)) over ledger as previous_closing_unit_id,
        lagInFrame(transaction_description) over ledger as previous_transaction_description
    from {{ ref('int_inventory_movements_enriched') }}
    window ledger as (
        partition by dataset_name, product_id, warehouse_id
        order by dataset_row_number
        rows between unbounded preceding and current row
    )
), continuity as (
    select
        *,
        opening_stock_quantity - previous_closing_quantity as continuity_delta_qty,
        isNull(previous_source_sequence) as is_ledger_start,
        toUInt8(ifNull(opening_stock_quantity != previous_closing_quantity, false)) as is_discontinuity,
        toUInt8(ifNull(opening_stock_quantity = previous_closing_quantity, false)) as is_continuous
    from predecessors
)

select
    *,
    multiIf(is_ledger_start, 'LEDGER_START', is_discontinuity,
            'OPENING_DIFFERS_FROM_PREVIOUS_CLOSING', 'CONTINUOUS') as boundary_reason
from continuity
