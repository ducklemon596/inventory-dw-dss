{{ config(materialized='table', engine='MergeTree()', order_by='warehouse_id') }}

select
    warehouse_id,
    warehouse_name
from {{ ref('stg_warehouses') }}
