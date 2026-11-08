-- SEGMENTS: One movement assigned to one locally anchored continuity segment
{{ config(materialized='table', engine='MergeTree()',
          order_by='(dataset_name, product_id, warehouse_id, dataset_row_number)') }}

with assigned as (
    select
        *,
        max(if(is_ledger_start or is_discontinuity, dataset_row_number, toUInt32(0)))
            over ledger as segment_start_sequence
    from {{ ref('int_inventory_ledger_ordered') }}
    window ledger as (
        partition by dataset_name, product_id, warehouse_id order by dataset_row_number
        rows between unbounded preceding and current row
    )
), anchored as (
    select
        *,
        -- JSON tuple encoding is unambiguous even when dataset names contain separators.
        toJSONString(tuple(dataset_name, product_id, warehouse_id, segment_start_sequence)) as segment_id,
        max(dataset_row_number) over segment as segment_end_sequence,
        argMin(opening_stock_quantity, dataset_row_number) over segment as segment_opening_quantity,
        argMin(movement_at, dataset_row_number) over segment as segment_started_at,
        argMax(movement_at, dataset_row_number) over segment as segment_ended_at,
        argMin(boundary_reason, dataset_row_number) over segment as segment_boundary_reason,
        sum(toDecimal128(recorded_delta_qty, 6)) over running_segment as segment_cumulative_delta_qty
    from assigned
    window
        segment as (partition by dataset_name, product_id, warehouse_id, segment_start_sequence
            order by dataset_row_number rows between unbounded preceding and unbounded following),
        running_segment as (partition by dataset_name, product_id, warehouse_id, segment_start_sequence
            order by dataset_row_number rows between unbounded preceding and current row)
)

select
    *,
    toDecimal128(segment_opening_quantity, 6) + segment_cumulative_delta_qty as reconstructed_closing_quantity
from anchored
