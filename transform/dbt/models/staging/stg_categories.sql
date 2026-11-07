-- =============================================================================
-- STAGING: Categories
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('category_id', []) }} as category_id,

        -- Business codes, names and attributes.
        {{ stg_text('category_name', ['-', 'null', 'none', 'n/a']) }} as category_name
    from {{ source('raw', 'category') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('category_id', 'UInt32', positive=true) }} as category_id,

    -- Business codes, names and attributes.
    CAST(category_name AS LowCardinality(String)) as category_name
from cleaned
