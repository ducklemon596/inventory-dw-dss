-- Unit labels are preserved exactly; conversion factors are governed separately for each product.
WITH cleaned AS (
    SELECT
        {{ stg_text('unit_id', []) }} AS unit_id,

        {{ stg_text('unit_code', []) }} AS unit_code
    FROM {{ source('raw', 'unit') }}
)

SELECT
    {{ stg_integer('unit_id', 'UInt32', positive=true) }} AS unit_id,

    CAST(unit_code AS LowCardinality(String)) AS unit_code
FROM cleaned
