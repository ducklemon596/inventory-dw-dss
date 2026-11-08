-- Inventory locations remain separate; source sales have no verified warehouse assignment.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='warehouse_id'
) }}

SELECT
    warehouse_id,
    warehouse_name
FROM {{ ref('stg_warehouses') }}
