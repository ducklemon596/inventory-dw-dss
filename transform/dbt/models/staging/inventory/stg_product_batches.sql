-- Batch identity includes product and expiry; a missing expiry does not create another lot.
WITH cleaned AS (
    SELECT
        {{ stg_text('batch_id', []) }} AS batch_id,
        {{ stg_text('product_id', []) }} AS product_id,

        {{ stg_text('batch_number', ['-']) }} AS batch_number,
        {{ stg_text('expiry_date', ['-', 'null', 'none', 'n/a', '0000-00-00']) }} AS expiry_date
    FROM {{ source('raw', 'product_batch') }}
)

SELECT
    {{ stg_integer('batch_id', 'UInt32', positive=true) }} AS product_batch_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} AS product_id,

    CAST(batch_number AS Nullable(String)) AS product_batch_number,
    {{ stg_date('expiry_date', 'Nullable(Date32)') }} AS expiration_date
FROM cleaned
