-- An invoice code groups source lines; event time, payment and fees remain on the lines.
WITH cleaned AS (
    SELECT
        {{ stg_text('invoice_id', []) }} AS invoice_id,

        {{ stg_text('invoice_number', []) }} AS invoice_number
    FROM {{ source('raw', 'sales_invoice') }}
)

SELECT
    {{ stg_integer('invoice_id', 'UInt32', positive=true) }} AS sales_invoice_id,

    CAST(invoice_number AS String) AS sales_invoice_number
FROM cleaned
