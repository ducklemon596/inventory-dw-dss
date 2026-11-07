-- =============================================================================
-- STAGING: Drug classes
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('drug_class_id', []) }} as drug_class_id,

        -- Business codes, names and attributes.
        {{ stg_text('drug_class_name', ['-', 'null', 'none', 'n/a']) }} as drug_class_name
    from {{ source('raw', 'drug_class') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('drug_class_id', 'UInt32', positive=true) }} as drug_class_id,

    -- Business codes, names and attributes.
    CAST(drug_class_name AS LowCardinality(String)) as drug_class_name
from cleaned
