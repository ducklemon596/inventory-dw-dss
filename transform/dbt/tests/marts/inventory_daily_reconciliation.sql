-- Reconcile directly with staging, including complete grain coverage and last row.
with expected as (
    select dataset_name, product_id, warehouse_id, toDate32(movement_at) as observation_date,
        argMax(tuple(inventory_movement_id, dataset_row_number, movement_at, closing_stock_quantity, closing_stock_unit_id),
               dataset_row_number) as last_row,
        min(dataset_row_number) as first_sequence,
        sum(received_quantity) as receipts, sum(issued_quantity) as issues,
        sum(received_quantity - issued_quantity) as delta, count() as movements
    from {{ ref('stg_inventory_movements') }}
    group by dataset_name, product_id, warehouse_id, observation_date
)
select coalesce(expected.product_id, actual.product_id) as product_id
from expected
full outer join {{ ref('fct_inventory_daily_observed') }} as actual
    on expected.dataset_name = actual.dataset_name and expected.product_id = actual.product_id
    and expected.warehouse_id = actual.warehouse_id and expected.observation_date = actual.observation_date
where expected.product_id is null or actual.product_id is null
    or actual.last_inventory_movement_id != expected.last_row.1
    or actual.last_source_sequence != expected.last_row.2
    or actual.last_movement_at != expected.last_row.3
    or actual.observed_closing_quantity != expected.last_row.4
    or actual.stock_unit_id != expected.last_row.5
    or actual.first_source_sequence != expected.first_sequence
    or actual.recorded_received_quantity != expected.receipts
    or actual.recorded_issued_quantity != expected.issues
    or actual.recorded_delta_qty != expected.delta
    or actual.movement_count != expected.movements
settings join_use_nulls = 1
