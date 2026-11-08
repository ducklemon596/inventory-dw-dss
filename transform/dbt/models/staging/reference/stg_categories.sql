-- Categories remain independent of drug classes; no hierarchy is inferred.
WITH cleaned AS (
    SELECT
        {{ stg_text('category_id', []) }} AS category_id,

        {{ stg_text('category_name', ['-', 'null', 'none', 'n/a']) }} AS category_name
    FROM {{ source('raw', 'category') }}
)

SELECT
    {{ stg_integer('category_id', 'UInt32', positive=true) }} AS category_id,

    CAST(category_name AS LowCardinality(String)) AS category_name
FROM cleaned
