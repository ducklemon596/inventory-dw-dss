-- Fees and percentages retain their recorded line scope; invoice allocation is unverified.
-- Optional batch and shift values remain missing when the source provides no value.
WITH cleaned AS (
    SELECT
        {{ stg_text('sales_line_id', []) }} AS sales_line_id,
        {{ stg_text('source_dataset', []) }} AS source_dataset,
        {{ stg_text('source_row_number', []) }} AS source_row_number,
        {{ stg_text('invoice_id', []) }} AS invoice_id,
        {{ stg_text('product_id', []) }} AS product_id,
        {{ stg_text('unit_id', []) }} AS unit_id,
        {{ stg_text('cashier_id', []) }} AS cashier_id,

        {{ stg_text('sold_at', []) }} AS sold_at,
        {{ stg_text('shift', []) }} AS shift,

        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} AS drug_name,
        {{ stg_text('manufacturer', ['-', 'null', 'none', 'n/a']) }} AS manufacturer,
        {{ stg_text('drug_class', ['-', 'null', 'none', 'n/a']) }} AS drug_class,
        {{ stg_text('category', ['-', 'null', 'none', 'n/a']) }} AS category,
        {{ stg_text('batch_and_expiry_date', []) }} AS batch_and_expiry_date,

        {{ stg_text('quantity', []) }} AS quantity,
        {{ stg_text('unit_price', []) }} AS unit_price,
        {{ stg_text('price_tier', ['-', 'null', 'none', 'n/a']) }} AS price_tier,
        {{ stg_text('discount_pct', ['-', 'null', 'none', 'n/a']) }} AS discount_pct,
        {{ stg_text('discount_amount', ['-', 'null', 'none', 'n/a']) }} AS discount_amount,
        {{ stg_text('service_fee', ['-', 'null', 'none', 'n/a']) }} AS service_fee,
        {{ stg_text('packaging_fee', ['-', 'null', 'none', 'n/a']) }} AS packaging_fee,
        {{ stg_text('subtotal', ['-', 'null', 'none', 'n/a']) }} AS subtotal,
        {{ stg_text('invoice_discount_pct', ['-', 'null', 'none', 'n/a']) }} AS invoice_discount_pct,
        {{ stg_text('promo_discount_pct', ['-', 'null', 'none', 'n/a']) }} AS promo_discount_pct,
        {{ stg_text('tax_pct', ['-', 'null', 'none', 'n/a']) }} AS tax_pct,
        {{ stg_text('additional_fee', ['-', 'null', 'none', 'n/a']) }} AS additional_fee,
        {{ stg_text('total_price', ['-', 'null', 'none', 'n/a']) }} AS total_price,

        {{ stg_text('payment_type', ['-', 'null', 'none', 'n/a']) }} AS payment_type,
        {{ stg_text('print_count', ['-', 'null', 'none', 'n/a']) }} AS print_count,
        {{ stg_text('is_member', ['-', 'null', 'none', 'n/a']) }} AS is_member,

        {{ stg_text('batch_id', ['-', 'null', 'none', 'n/a']) }} AS batch_id,

        {{ stg_text('shift_date', ['-', 'null', 'none', 'n/a', '0000-00-00']) }} AS shift_date,
        {{ stg_text('shift_period', ['-', 'null', 'none', 'n/a']) }} AS shift_period,
        {{ stg_text('shift_cashier_code', []) }} AS shift_cashier_code,

        {{ stg_text('price_tier_number', ['-', 'null', 'none', 'n/a']) }} AS price_tier_number
    FROM {{ source('raw', 'sales_line') }}
)

SELECT
    {{ stg_integer('sales_line_id', 'UInt32', positive=true) }} AS sales_invoice_line_id,
    CAST(source_dataset AS LowCardinality(String)) AS dataset_name,
    {{ stg_integer('source_row_number', 'UInt32', positive=true) }} AS dataset_row_number,
    {{ stg_integer('invoice_id', 'UInt32', positive=true) }} AS sales_invoice_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} AS product_id,
    {{ stg_integer('unit_id', 'UInt32', positive=true) }} AS unit_id,
    {{ stg_integer('cashier_id', 'UInt32', positive=true) }} AS cashier_id,

    {{ stg_timestamp('sold_at', 'DateTime64(6)') }} AS sold_at,
    CAST(shift AS Nullable(String)) AS shift_label,

    CAST(drug_name AS String) AS product_name,
    CAST(manufacturer AS LowCardinality(Nullable(String))) AS manufacturer_name,
    CAST(drug_class AS LowCardinality(Nullable(String))) AS drug_class_name,
    CAST(category AS LowCardinality(Nullable(String))) AS category_name,
    CAST(batch_and_expiry_date AS Nullable(String)) AS product_batch_label,

    {{ stg_decimal('quantity', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} AS sold_quantity,
    {{ stg_decimal('unit_price', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} AS unit_price,
    CAST(price_tier AS LowCardinality(Nullable(String))) AS price_tier_label,
    {{ stg_decimal(
        'discount_pct', 'Nullable(Decimal(9, 4))',
        precision=9, scale=4, percentage=true
    ) }} AS discount_percentage,
    {{ stg_decimal(
        'discount_amount', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS discount_amount,
    {{ stg_decimal(
        'service_fee', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS service_fee_amount,
    {{ stg_decimal(
        'packaging_fee', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS packaging_fee_amount,
    {{ stg_decimal(
        'subtotal', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS subtotal_amount,
    {{ stg_decimal(
        'invoice_discount_pct', 'Nullable(Decimal(9, 4))',
        precision=9, scale=4, percentage=true
    ) }} AS invoice_discount_percentage,
    {{ stg_decimal(
        'promo_discount_pct', 'Nullable(Decimal(9, 4))',
        precision=9, scale=4, percentage=true
    ) }} AS promotional_discount_percentage,
    {{ stg_decimal('tax_pct', 'Nullable(Decimal(9, 4))', precision=9, scale=4, percentage=true) }} AS tax_percentage,
    {{ stg_decimal(
        'additional_fee', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS additional_fee_amount,
    {{ stg_decimal(
        'total_price', 'Nullable(Decimal(18, 6))',
        precision=18, scale=6, percentage=false
    ) }} AS total_amount,

    {{ stg_domain(
        'payment_type',
        'LowCardinality(Nullable(String))',
        ['TUNAI', 'KARTU', 'KREDIT']
    ) }} AS payment_method,
    {{ stg_integer('print_count', 'Nullable(UInt16)', positive=false) }} AS document_print_count,
    {{ stg_domain('is_member', 'LowCardinality(Nullable(String))', ['NON MEMBER', 'MEMBER']) }} AS membership_status,

    {{ stg_integer('batch_id', 'Nullable(UInt32)', positive=true) }} AS product_batch_id,

    {{ stg_date('shift_date', 'Nullable(Date32)') }} AS shift_date,
    {{ stg_domain('shift_period', 'LowCardinality(Nullable(String))', ['PAGI', 'SORE']) }} AS shift_period,
    CAST(shift_cashier_code AS Nullable(String)) AS shift_cashier_code,

    {{ stg_integer('price_tier_number', 'Nullable(UInt8)', positive=true) }} AS price_tier_number
FROM cleaned
