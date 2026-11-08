with cleaned as (
    select
        {{ stg_text('category_id', []) }} as category_id,

        {{ stg_text('category_name', ['-', 'null', 'none', 'n/a']) }} as category_name
    from {{ source('raw', 'category') }}
)

select
    {{ stg_integer('category_id', 'UInt32', positive=true) }} as category_id,

    CAST(category_name AS LowCardinality(String)) as category_name
from cleaned
