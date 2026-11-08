{{ config(materialized='table', engine='MergeTree()', order_by='unit_id') }}

select
    unit_id,
    unit_code
from {{ ref('stg_units') }}
