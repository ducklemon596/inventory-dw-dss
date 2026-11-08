-- Preserve each recorded inventory location; these records do not assign warehouses to sales.
WITH cleaned AS (
    SELECT
        {{ stg_text('warehouse_id', []) }} AS warehouse_id,

        {{ stg_text('warehouse_name', ['-', 'null', 'none', 'n/a']) }} AS warehouse_name
    FROM {{ source('raw', 'warehouse') }}
)

SELECT
    {{ stg_integer('warehouse_id', 'UInt32', positive=true) }} AS warehouse_id,

    CAST(warehouse_name AS LowCardinality(String)) AS warehouse_name
FROM cleaned
