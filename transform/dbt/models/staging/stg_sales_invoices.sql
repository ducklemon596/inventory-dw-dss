-- =============================================================================
-- STAGING: Sales invoices
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('invoice_id', []) }} as invoice_id,

        -- Business codes, names and attributes.
        {{ stg_text('invoice_number', []) }} as invoice_number
    from {{ source('raw', 'sales_invoice') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('invoice_id', 'UInt32', positive=true) }} as sales_invoice_id,

    -- Business codes, names and attributes.
    CAST(invoice_number AS String) as sales_invoice_number
from cleaned
