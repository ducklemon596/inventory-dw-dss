with cleaned as (
    select
        {{ stg_text('unit_id', []) }} as unit_id,

        {{ stg_text('unit_code', []) }} as unit_code
    from {{ source('raw', 'unit') }}
)

select
    {{ stg_integer('unit_id', 'UInt32', positive=true) }} as unit_id,

    CAST(unit_code AS LowCardinality(String)) as unit_code
from cleaned
