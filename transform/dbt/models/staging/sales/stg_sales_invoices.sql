with cleaned as (
    select
        {{ stg_text('invoice_id', []) }} as invoice_id,

        {{ stg_text('invoice_number', []) }} as invoice_number
    from {{ source('raw', 'sales_invoice') }}
)

select
    {{ stg_integer('invoice_id', 'UInt32', positive=true) }} as sales_invoice_id,

    CAST(invoice_number AS String) as sales_invoice_number
from cleaned
