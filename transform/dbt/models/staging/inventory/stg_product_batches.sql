with cleaned as (
    select
        {{ stg_text('batch_id', []) }} as batch_id,
        {{ stg_text('product_id', []) }} as product_id,

        {{ stg_text('batch_number', ['-']) }} as batch_number,
        {{ stg_text('expiry_date', ['-', 'null', 'none', 'n/a', '0000-00-00']) }} as expiry_date
    from {{ source('raw', 'product_batch') }}
)

select
    {{ stg_integer('batch_id', 'UInt32', positive=true) }} as product_batch_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,

    CAST(batch_number AS Nullable(String)) as product_batch_number,
    {{ stg_date('expiry_date', 'Nullable(Date32)') }} as expiration_date
from cleaned
