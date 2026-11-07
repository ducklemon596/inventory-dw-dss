-- =============================================================================
-- STAGING: Products
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('product_id', []) }} as product_id,

        -- Business codes, names and attributes.
        {{ stg_text('drug_code', []) }} as drug_code,
        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} as drug_name,

        -- Identity and relationships.
        {{ stg_text('manufacturer_id', ['-', 'null', 'none', 'n/a']) }} as manufacturer_id,
        {{ stg_text('drug_class_id', ['-', 'null', 'none', 'n/a']) }} as drug_class_id,
        {{ stg_text('category_id', ['-', 'null', 'none', 'n/a']) }} as category_id
    from {{ source('raw', 'product') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,

    -- Business codes, names and attributes.
    CAST(drug_code AS String) as product_code,
    CAST(drug_name AS Nullable(String)) as product_name,

    -- Identity and relationships.
    {{ stg_integer('manufacturer_id', 'Nullable(UInt32)', positive=true) }} as manufacturer_id,
    {{ stg_integer('drug_class_id', 'Nullable(UInt32)', positive=true) }} as drug_class_id,
    {{ stg_integer('category_id', 'Nullable(UInt32)', positive=true) }} as category_id
from cleaned
