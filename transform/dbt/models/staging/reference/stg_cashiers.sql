-- Preserve the pseudonymous cashier code separately from its numeric identity.
WITH cleaned AS (
    SELECT
        {{ stg_text('cashier_id', []) }} AS cashier_id,

        {{ stg_text('source_code', []) }} AS source_code
    FROM {{ source('raw', 'cashier') }}
)

SELECT
    {{ stg_integer('cashier_id', 'UInt32', positive=true) }} AS cashier_id,

    CAST(source_code AS String) AS cashier_code
FROM cleaned
