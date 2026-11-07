-- =============================================================================
-- STAGING: Units
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('unit_id', []) }} as unit_id,

        -- Business codes, names and attributes.
        {{ stg_text('unit_code', []) }} as unit_code
    from {{ source('raw', 'unit') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('unit_id', 'UInt32', positive=true) }} as unit_id,

    -- Business codes, names and attributes.
    CAST(unit_code AS LowCardinality(String)) as unit_code
from cleaned
