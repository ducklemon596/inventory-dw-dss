with cleaned as (
    select
        {{ stg_text('warehouse_id', []) }} as warehouse_id,

        {{ stg_text('warehouse_name', ['-', 'null', 'none', 'n/a']) }} as warehouse_name
    from {{ source('raw', 'warehouse') }}
)

select
    {{ stg_integer('warehouse_id', 'UInt32', positive=true) }} as warehouse_id,

    CAST(warehouse_name AS LowCardinality(String)) as warehouse_name
from cleaned
