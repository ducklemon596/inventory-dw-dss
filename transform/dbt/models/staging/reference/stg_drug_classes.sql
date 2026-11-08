-- Preserve the source drug classifications without inferring therapeutic groups.
WITH cleaned AS (
    SELECT
        {{ stg_text('drug_class_id', []) }} AS drug_class_id,

        {{ stg_text('drug_class_name', ['-', 'null', 'none', 'n/a']) }} AS drug_class_name
    FROM {{ source('raw', 'drug_class') }}
)

SELECT
    {{ stg_integer('drug_class_id', 'UInt32', positive=true) }} AS drug_class_id,

    CAST(drug_class_name AS LowCardinality(String)) AS drug_class_name
FROM cleaned
