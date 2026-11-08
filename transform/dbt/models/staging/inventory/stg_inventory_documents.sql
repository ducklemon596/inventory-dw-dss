-- Document codes can span warehouses and times, so movement attributes stay on movement rows.
WITH cleaned AS (
    SELECT
        {{ stg_text('document_id', []) }} AS document_id,

        {{ stg_text('document_number', []) }} AS document_number
    FROM {{ source('raw', 'inventory_document') }}
)

SELECT
    {{ stg_integer('document_id', 'UInt32', positive=true) }} AS inventory_document_id,

    CAST(document_number AS String) AS inventory_document_number
FROM cleaned
