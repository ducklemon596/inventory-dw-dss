-- FACT: Export / product / warehouse / observed date; no generated calendar rows
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, warehouse_id, observation_date)'
) }}

WITH observations AS (
    SELECT
        *,
        max(movement_at) OVER (
            PARTITION BY dataset_name, product_id, warehouse_id, movement_date
        ) AS latest_day_timestamp
    FROM {{ ref('fct_inventory_movement') }}
),

daily AS (
    SELECT
        dataset_name,
        product_id,
        warehouse_id,
        movement_date AS observation_date,
        -- A single tuple selects a coherent complete last observation by source order.
        argMax(
            tuple(
                inventory_movement_id,
                dataset_row_number,
                movement_at,
                closing_stock_quantity,
                closing_stock_unit_id,
                segment_id
            ),
            dataset_row_number
        ) AS last_observation,
        min(dataset_row_number) AS first_source_sequence,
        sum(received_quantity) AS recorded_received_quantity,
        sum(issued_quantity) AS recorded_issued_quantity,
        sum(recorded_delta_qty) AS recorded_delta_qty,
        count() AS movement_count,
        countIf(is_discontinuity) AS discontinuity_count,
        uniqExact(segment_id) AS segment_count,
        uniqExact(closing_stock_unit_id) AS stock_unit_count,
        uniqExactIf(closing_stock_quantity, movement_at = latest_day_timestamp) AS latest_timestamp_closing_count
    FROM observations
    GROUP BY
        dataset_name,
        product_id,
        warehouse_id,
        movement_date
)

SELECT
    dataset_name,
    product_id,
    warehouse_id,
    observation_date,
    last_observation.1 AS last_inventory_movement_id,
    last_observation.2 AS last_source_sequence,
    last_observation.3 AS last_movement_at,
    last_observation.4 AS observed_closing_quantity,
    last_observation.5 AS stock_unit_id,
    last_observation.6 AS last_segment_id,
    first_source_sequence,
    recorded_received_quantity,
    recorded_issued_quantity,
    recorded_delta_qty,
    movement_count,
    discontinuity_count,
    segment_count,
    stock_unit_count,
    toUInt8(discontinuity_count > 0) AS has_discontinuity,
    toUInt8(last_observation.4 < 0) AS has_negative_closing_stock,
    toUInt8(latest_timestamp_closing_count > 1) AS has_ambiguous_latest_timestamp
FROM daily
