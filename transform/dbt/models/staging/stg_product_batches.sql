-- =============================================================================
-- STAGING: Product batches
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('batch_id', []) }} as batch_id,
        {{ stg_text('product_id', []) }} as product_id,

        -- Business codes, names and attributes.
        {{ stg_text('batch_number', ['-']) }} as batch_number,
        {{ stg_text('expiry_date', ['-', 'null', 'none', 'n/a', '0000-00-00']) }} as expiry_date
    from {{ source('raw', 'product_batch') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('batch_id', 'UInt32', positive=true) }} as product_batch_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,

    -- Business codes, names and attributes.
    CAST(batch_number AS Nullable(String)) as product_batch_number,
    {{ stg_date('expiry_date', 'Nullable(Date32)') }} as expiration_date
from cleaned
