-- FACT: Export / product / warehouse / observed date; no generated calendar rows
{{ config(materialized='table', engine='MergeTree()',
          order_by='(dataset_name, product_id, warehouse_id, observation_date)') }}

with observations as (
    select
        *,
        max(movement_at) over (
            partition by dataset_name, product_id, warehouse_id, movement_date
        ) as latest_day_timestamp
    from {{ ref('fct_inventory_movement') }}
), daily as (
    select
        dataset_name,
        product_id,
        warehouse_id,
        movement_date as observation_date,
        -- A single tuple selects a coherent complete last observation by source order.
        argMax(tuple(inventory_movement_id, dataset_row_number, movement_at,
                     closing_stock_quantity, closing_stock_unit_id, segment_id),
               dataset_row_number) as last_observation,
        min(dataset_row_number) as first_source_sequence,
        sum(received_quantity) as recorded_received_quantity,
        sum(issued_quantity) as recorded_issued_quantity,
        sum(recorded_delta_qty) as recorded_delta_qty,
        count() as movement_count,
        countIf(is_discontinuity) as discontinuity_count,
        uniqExact(segment_id) as segment_count,
        uniqExact(closing_stock_unit_id) as stock_unit_count,
        uniqExactIf(closing_stock_quantity, movement_at = latest_day_timestamp) as latest_timestamp_closing_count
    from observations
    group by dataset_name, product_id, warehouse_id, movement_date
)

select
    dataset_name,
    product_id,
    warehouse_id,
    observation_date,
    last_observation.1 as last_inventory_movement_id,
    last_observation.2 as last_source_sequence,
    last_observation.3 as last_movement_at,
    last_observation.4 as observed_closing_quantity,
    last_observation.5 as stock_unit_id,
    last_observation.6 as last_segment_id,
    first_source_sequence,
    recorded_received_quantity,
    recorded_issued_quantity,
    recorded_delta_qty,
    movement_count,
    discontinuity_count,
    segment_count,
    stock_unit_count,
    toUInt8(discontinuity_count > 0) as has_discontinuity,
    toUInt8(last_observation.4 < 0) as has_negative_closing_stock,
    toUInt8(latest_timestamp_closing_count > 1) as has_ambiguous_latest_timestamp
from daily
