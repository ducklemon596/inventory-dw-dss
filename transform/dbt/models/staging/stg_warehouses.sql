-- =============================================================================
-- STAGING: Warehouses
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('warehouse_id', []) }} as warehouse_id,

        -- Business codes, names and attributes.
        {{ stg_text('warehouse_name', ['-', 'null', 'none', 'n/a']) }} as warehouse_name
    from {{ source('raw', 'warehouse') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('warehouse_id', 'UInt32', positive=true) }} as warehouse_id,

    -- Business codes, names and attributes.
    CAST(warehouse_name AS LowCardinality(String)) as warehouse_name
from cleaned
