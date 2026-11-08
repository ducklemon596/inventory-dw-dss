-- Unit labels describe quantity roles; conversion factors belong to product-specific governed mappings.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='unit_id'
) }}

SELECT
    unit_id,
    unit_code
FROM {{ ref('stg_units') }}
