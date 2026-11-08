with cleaned as (
    select
        {{ stg_text('document_id', []) }} as document_id,

        {{ stg_text('document_number', []) }} as document_number
    from {{ source('raw', 'inventory_document') }}
)

select
    {{ stg_integer('document_id', 'UInt32', positive=true) }} as inventory_document_id,

    CAST(document_number AS String) as inventory_document_number
from cleaned
