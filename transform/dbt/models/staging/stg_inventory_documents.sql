-- =============================================================================
-- STAGING: Inventory documents
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity and relationships.
        {{ stg_text('document_id', []) }} as document_id,

        -- Business codes, names and attributes.
        {{ stg_text('document_number', []) }} as document_number
    from {{ source('raw', 'inventory_document') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity and relationships.
    {{ stg_integer('document_id', 'UInt32', positive=true) }} as inventory_document_id,

    -- Business codes, names and attributes.
    CAST(document_number AS String) as inventory_document_number
from cleaned
