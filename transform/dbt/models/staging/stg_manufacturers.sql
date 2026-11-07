-- =============================================================================
-- STAGING: Manufacturers
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('manufacturer_id', []) }} as manufacturer_id,

        -- Business codes, names and attributes.
        {{ stg_text('manufacturer_name', ['-', 'null', 'none', 'n/a']) }} as manufacturer_name
    from {{ source('raw', 'manufacturer') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('manufacturer_id', 'UInt32', positive=true) }} as manufacturer_id,

    -- Business codes, names and attributes.
    CAST(manufacturer_name AS LowCardinality(String)) as manufacturer_name
from cleaned
