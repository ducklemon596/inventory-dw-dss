with cleaned as (
    select
        {{ stg_text('product_id', []) }} as product_id,

        {{ stg_text('drug_code', []) }} as drug_code,
        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} as drug_name,

        {{ stg_text('manufacturer_id', ['-', 'null', 'none', 'n/a']) }} as manufacturer_id,
        {{ stg_text('drug_class_id', ['-', 'null', 'none', 'n/a']) }} as drug_class_id,
        {{ stg_text('category_id', ['-', 'null', 'none', 'n/a']) }} as category_id
    from {{ source('raw', 'product') }}
)

select
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,

    CAST(drug_code AS String) as product_code,
    CAST(drug_name AS Nullable(String)) as product_name,

    {{ stg_integer('manufacturer_id', 'Nullable(UInt32)', positive=true) }} as manufacturer_id,
    {{ stg_integer('drug_class_id', 'Nullable(UInt32)', positive=true) }} as drug_class_id,
    {{ stg_integer('category_id', 'Nullable(UInt32)', positive=true) }} as category_id
from cleaned
