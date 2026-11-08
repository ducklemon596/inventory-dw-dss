with cleaned as (
    select
        {{ stg_text('cashier_id', []) }} as cashier_id,

        {{ stg_text('source_code', []) }} as source_code
    from {{ source('raw', 'cashier') }}
)

select
    {{ stg_integer('cashier_id', 'UInt32', positive=true) }} as cashier_id,

    CAST(source_code AS String) as cashier_code
from cleaned
