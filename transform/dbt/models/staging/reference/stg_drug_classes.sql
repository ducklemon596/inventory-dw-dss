with cleaned as (
    select
        {{ stg_text('drug_class_id', []) }} as drug_class_id,

        {{ stg_text('drug_class_name', ['-', 'null', 'none', 'n/a']) }} as drug_class_name
    from {{ source('raw', 'drug_class') }}
)

select
    {{ stg_integer('drug_class_id', 'UInt32', positive=true) }} as drug_class_id,

    CAST(drug_class_name AS LowCardinality(String)) as drug_class_name
from cleaned
