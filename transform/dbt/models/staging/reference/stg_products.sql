-- Current catalog labels stay separate from the descriptions recorded on transaction lines.
WITH cleaned AS (
    SELECT
        {{ stg_text('product_id', []) }} AS product_id,

        {{ stg_text('drug_code', []) }} AS drug_code,
        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} AS drug_name,

        {{ stg_text('manufacturer_id', ['-', 'null', 'none', 'n/a']) }} AS manufacturer_id,
        {{ stg_text('drug_class_id', ['-', 'null', 'none', 'n/a']) }} AS drug_class_id,
        {{ stg_text('category_id', ['-', 'null', 'none', 'n/a']) }} AS category_id
    FROM {{ source('raw', 'product') }}
)

SELECT
    {{ stg_integer('product_id', 'UInt32', positive=true) }} AS product_id,

    CAST(drug_code AS String) AS product_code,
    CAST(drug_name AS Nullable(String)) AS product_name,

    {{ stg_integer('manufacturer_id', 'Nullable(UInt32)', positive=true) }} AS manufacturer_id,
    {{ stg_integer('drug_class_id', 'Nullable(UInt32)', positive=true) }} AS drug_class_id,
    {{ stg_integer('category_id', 'Nullable(UInt32)', positive=true) }} AS category_id
FROM cleaned
