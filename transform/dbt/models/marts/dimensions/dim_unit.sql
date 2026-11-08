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

-- A dimensional placeholder for missing evidence, never a physical unit or conversion target.
UNION ALL

SELECT
    toUInt32(0) AS unit_id,
    CAST('NOT_VERIFIED_STOCK_UNIT' AS LowCardinality(String)) AS unit_code
