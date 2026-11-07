-- =============================================================================
-- STAGING: Cashiers
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('cashier_id', []) }} as cashier_id,

        -- Business codes, names and attributes.
        {{ stg_text('source_code', []) }} as source_code
    from {{ source('raw', 'cashier') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('cashier_id', 'UInt32', positive=true) }} as cashier_id,

    -- Business codes, names and attributes.
    CAST(source_code AS String) as cashier_code
from cleaned
