-- Manufacturer labels remain distinct; catalog entries are not merged by similar spelling.
WITH cleaned AS (
    SELECT
        {{ stg_text('manufacturer_id', []) }} AS manufacturer_id,

        {{ stg_text('manufacturer_name', ['-', 'null', 'none', 'n/a']) }} AS manufacturer_name
    FROM {{ source('raw', 'manufacturer') }}
)

SELECT
    {{ stg_integer('manufacturer_id', 'UInt32', positive=true) }} AS manufacturer_id,

    CAST(manufacturer_name AS LowCardinality(String)) AS manufacturer_name
FROM cleaned
