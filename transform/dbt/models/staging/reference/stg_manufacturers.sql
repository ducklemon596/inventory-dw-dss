with cleaned as (
    select
        {{ stg_text('manufacturer_id', []) }} as manufacturer_id,

        {{ stg_text('manufacturer_name', ['-', 'null', 'none', 'n/a']) }} as manufacturer_name
    from {{ source('raw', 'manufacturer') }}
)

select
    {{ stg_integer('manufacturer_id', 'UInt32', positive=true) }} as manufacturer_id,

    CAST(manufacturer_name AS LowCardinality(String)) as manufacturer_name
from cleaned
