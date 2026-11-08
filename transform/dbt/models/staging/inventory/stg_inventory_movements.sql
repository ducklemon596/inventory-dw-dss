-- Keep negative balances and the recorded RETURN direction; classification does not determine quantity signs.
-- UNKNOWN remains a recorded classification rather than an inferred inventory operation.
WITH cleaned AS (
    SELECT
        {{ stg_text('movement_id', []) }} AS movement_id,
        {{ stg_text('source_dataset', []) }} AS source_dataset,
        {{ stg_text('source_row_number', []) }} AS source_row_number,
        {{ stg_text('document_id', []) }} AS document_id,
        {{ stg_text('product_id', []) }} AS product_id,
        {{ stg_text('warehouse_id', []) }} AS warehouse_id,

        {{ stg_text('occurred_at', []) }} AS occurred_at,

        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} AS drug_name,
        {{ stg_text('drug_class', ['-', 'null', 'none', 'n/a']) }} AS drug_class,
        {{ stg_text('category', ['-', 'null', 'none', 'n/a']) }} AS category,
        {{ stg_text('drug_type', ['-', 'null', 'none', 'n/a']) }} AS drug_type,
        {{ stg_text('status', ['-', 'null', 'none', 'n/a']) }} AS status,

        {{ stg_text('description', []) }} AS description,

        {{ stg_text('initial_stock', []) }} AS initial_stock,
        {{ stg_text('stock_in', []) }} AS stock_in,
        {{ stg_text('stock_out', []) }} AS stock_out,
        {{ stg_text('remaining_stock', []) }} AS remaining_stock,

        {{ stg_text('initial_unit_id', []) }} AS initial_unit_id,
        {{ stg_text('in_unit_id', []) }} AS in_unit_id,
        {{ stg_text('out_unit_id', []) }} AS out_unit_id,
        {{ stg_text('remaining_unit_id', []) }} AS remaining_unit_id,

        {{ stg_text('transaction_type', ['-', 'null', 'none', 'n/a']) }} AS transaction_type,
        {{ stg_text('supplier_name', ['-', 'null', 'none', 'n/a']) }} AS supplier_name,
        {{ stg_text('referenced_invoice_number', []) }} AS referenced_invoice_number,
        {{ stg_text('patient_code', []) }} AS patient_code
    FROM {{ source('raw', 'inventory_movement') }}
)

SELECT
    {{ stg_integer('movement_id', 'UInt32', positive=true) }} AS inventory_movement_id,
    CAST(source_dataset AS LowCardinality(String)) AS dataset_name,
    {{ stg_integer('source_row_number', 'UInt32', positive=true) }} AS dataset_row_number,
    {{ stg_integer('document_id', 'UInt32', positive=true) }} AS inventory_document_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} AS product_id,
    {{ stg_integer('warehouse_id', 'UInt32', positive=true) }} AS warehouse_id,

    {{ stg_timestamp('occurred_at', 'DateTime64(6)') }} AS movement_at,

    CAST(drug_name AS String) AS product_name,
    CAST(drug_class AS LowCardinality(Nullable(String))) AS drug_class_name,
    CAST(category AS LowCardinality(Nullable(String))) AS category_name,
    {{ stg_domain(
        'drug_type',
        'LowCardinality(Nullable(String))',
        ['NON KONSINYASI', 'KONSINYASI']
    ) }} AS consignment_status,
    {{ stg_domain('status', 'LowCardinality(Nullable(String))', ['AKTIF']) }} AS product_status,

    CAST(description AS Nullable(String)) AS transaction_description,

    {{ stg_decimal(
        'initial_stock', 'Decimal(18, 6)',
        precision=18, scale=6, percentage=false
    ) }} AS opening_stock_quantity,
    {{ stg_decimal('stock_in', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} AS received_quantity,
    {{ stg_decimal('stock_out', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} AS issued_quantity,
    {{ stg_decimal(
        'remaining_stock', 'Decimal(18, 6)',
        precision=18, scale=6, percentage=false
    ) }} AS closing_stock_quantity,

    {{ stg_integer('initial_unit_id', 'UInt32', positive=true) }} AS opening_stock_unit_id,
    {{ stg_integer('in_unit_id', 'UInt32', positive=true) }} AS received_unit_id,
    {{ stg_integer('out_unit_id', 'UInt32', positive=true) }} AS issued_unit_id,
    {{ stg_integer('remaining_unit_id', 'UInt32', positive=true) }} AS closing_stock_unit_id,

    {{ stg_domain(
        'transaction_type',
        'LowCardinality(Nullable(String))',
        ['SALE', 'TRANSFER', 'PURCHASE', 'UNKNOWN', 'IMPORT_STOCKTAKE', 'IMPORT_PRODUCT', 'RETURN', 'CREATE_PRODUCT']
    ) }} AS transaction_type,
    CAST(supplier_name AS Nullable(String)) AS supplier_name,
    CAST(referenced_invoice_number AS Nullable(String)) AS referenced_sales_invoice_number,
    CAST(patient_code AS Nullable(String)) AS patient_code
FROM cleaned
