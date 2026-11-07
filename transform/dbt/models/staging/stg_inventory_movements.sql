-- =============================================================================
-- STAGING: Inventory movements
-- =============================================================================
-- One row per business record; normalization does not filter or aggregate.

-- 01. Normalize whitespace and field-specific missing values.
with cleaned as (
    select
        -- Identity, dataset and relationships.
        {{ stg_text('movement_id', []) }} as movement_id,
        {{ stg_text('source_dataset', []) }} as source_dataset,
        {{ stg_text('source_row_number', []) }} as source_row_number,
        {{ stg_text('document_id', []) }} as document_id,
        {{ stg_text('product_id', []) }} as product_id,
        {{ stg_text('warehouse_id', []) }} as warehouse_id,

        -- Movement time.
        {{ stg_text('occurred_at', []) }} as occurred_at,

        -- Product descriptions and status.
        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} as drug_name,
        {{ stg_text('drug_class', ['-', 'null', 'none', 'n/a']) }} as drug_class,
        {{ stg_text('category', ['-', 'null', 'none', 'n/a']) }} as category,
        {{ stg_text('drug_type', ['-', 'null', 'none', 'n/a']) }} as drug_type,
        {{ stg_text('status', ['-', 'null', 'none', 'n/a']) }} as status,

        -- Original transaction description.
        {{ stg_text('description', []) }} as description,

        -- Opening balance, receipts, issues and closing balance.
        {{ stg_text('initial_stock', []) }} as initial_stock,
        {{ stg_text('stock_in', []) }} as stock_in,
        {{ stg_text('stock_out', []) }} as stock_out,
        {{ stg_text('remaining_stock', []) }} as remaining_stock,

        -- Units for each inventory quantity.
        {{ stg_text('initial_unit_id', []) }} as initial_unit_id,
        {{ stg_text('in_unit_id', []) }} as in_unit_id,
        {{ stg_text('out_unit_id', []) }} as out_unit_id,
        {{ stg_text('remaining_unit_id', []) }} as remaining_unit_id,

        -- Transaction classification and referenced parties/documents.
        {{ stg_text('transaction_type', ['-', 'null', 'none', 'n/a']) }} as transaction_type,
        {{ stg_text('supplier_name', ['-', 'null', 'none', 'n/a']) }} as supplier_name,
        {{ stg_text('referenced_invoice_number', []) }} as referenced_invoice_number,
        {{ stg_text('patient_code', []) }} as patient_code
    from {{ source('raw', 'inventory_movement') }}
)

-- 02. Validate values, apply compact types and expose business columns.
select
    -- Identity, dataset and relationships.
    {{ stg_integer('movement_id', 'UInt32', positive=true) }} as inventory_movement_id,
    CAST(source_dataset AS LowCardinality(String)) as dataset_name,
    {{ stg_integer('source_row_number', 'UInt32', positive=true) }} as dataset_row_number,
    {{ stg_integer('document_id', 'UInt32', positive=true) }} as inventory_document_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,
    {{ stg_integer('warehouse_id', 'UInt32', positive=true) }} as warehouse_id,

    -- Movement time.
    {{ stg_timestamp('occurred_at', 'DateTime64(6)') }} as movement_at,

    -- Product descriptions and status.
    CAST(drug_name AS String) as product_name,
    CAST(drug_class AS LowCardinality(Nullable(String))) as drug_class_name,
    CAST(category AS LowCardinality(Nullable(String))) as category_name,
    {{ stg_domain('drug_type', 'LowCardinality(Nullable(String))', ['NON KONSINYASI', 'KONSINYASI']) }} as consignment_status,
    {{ stg_domain('status', 'LowCardinality(Nullable(String))', ['AKTIF']) }} as product_status,

    -- Original transaction description.
    CAST(description AS Nullable(String)) as transaction_description,

    -- Opening balance, receipts, issues and closing balance.
    {{ stg_decimal('initial_stock', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as opening_stock_quantity,
    {{ stg_decimal('stock_in', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as received_quantity,
    {{ stg_decimal('stock_out', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as issued_quantity,
    {{ stg_decimal('remaining_stock', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as closing_stock_quantity,

    -- Units for each inventory quantity.
    {{ stg_integer('initial_unit_id', 'UInt32', positive=true) }} as opening_stock_unit_id,
    {{ stg_integer('in_unit_id', 'UInt32', positive=true) }} as received_unit_id,
    {{ stg_integer('out_unit_id', 'UInt32', positive=true) }} as issued_unit_id,
    {{ stg_integer('remaining_unit_id', 'UInt32', positive=true) }} as closing_stock_unit_id,

    -- Transaction classification and referenced parties/documents.
    {{ stg_domain('transaction_type', 'LowCardinality(Nullable(String))', ['SALE', 'TRANSFER', 'PURCHASE', 'UNKNOWN', 'IMPORT_STOCKTAKE', 'IMPORT_PRODUCT', 'RETURN', 'CREATE_PRODUCT']) }} as transaction_type,
    CAST(supplier_name AS Nullable(String)) as supplier_name,
    CAST(referenced_invoice_number AS Nullable(String)) as referenced_sales_invoice_number,
    CAST(patient_code AS Nullable(String)) as patient_code
from cleaned
