with cleaned as (
    select
        {{ stg_text('sales_line_id', []) }} as sales_line_id,
        {{ stg_text('source_dataset', []) }} as source_dataset,
        {{ stg_text('source_row_number', []) }} as source_row_number,
        {{ stg_text('invoice_id', []) }} as invoice_id,
        {{ stg_text('product_id', []) }} as product_id,
        {{ stg_text('unit_id', []) }} as unit_id,
        {{ stg_text('cashier_id', []) }} as cashier_id,

        -- Sale time and original shift designation.
        {{ stg_text('sold_at', []) }} as sold_at,
        {{ stg_text('shift', []) }} as shift,

        -- Product and batch descriptions.
        {{ stg_text('drug_name', ['-', 'null', 'none', 'n/a']) }} as drug_name,
        {{ stg_text('manufacturer', ['-', 'null', 'none', 'n/a']) }} as manufacturer,
        {{ stg_text('drug_class', ['-', 'null', 'none', 'n/a']) }} as drug_class,
        {{ stg_text('category', ['-', 'null', 'none', 'n/a']) }} as category,
        {{ stg_text('batch_and_expiry_date', []) }} as batch_and_expiry_date,

        -- Quantities, pricing, discounts, fees and tax.
        {{ stg_text('quantity', []) }} as quantity,
        {{ stg_text('unit_price', []) }} as unit_price,
        {{ stg_text('price_tier', ['-', 'null', 'none', 'n/a']) }} as price_tier,
        {{ stg_text('discount_pct', ['-', 'null', 'none', 'n/a']) }} as discount_pct,
        {{ stg_text('discount_amount', ['-', 'null', 'none', 'n/a']) }} as discount_amount,
        {{ stg_text('service_fee', ['-', 'null', 'none', 'n/a']) }} as service_fee,
        {{ stg_text('packaging_fee', ['-', 'null', 'none', 'n/a']) }} as packaging_fee,
        {{ stg_text('subtotal', ['-', 'null', 'none', 'n/a']) }} as subtotal,
        {{ stg_text('invoice_discount_pct', ['-', 'null', 'none', 'n/a']) }} as invoice_discount_pct,
        {{ stg_text('promo_discount_pct', ['-', 'null', 'none', 'n/a']) }} as promo_discount_pct,
        {{ stg_text('tax_pct', ['-', 'null', 'none', 'n/a']) }} as tax_pct,
        {{ stg_text('additional_fee', ['-', 'null', 'none', 'n/a']) }} as additional_fee,
        {{ stg_text('total_price', ['-', 'null', 'none', 'n/a']) }} as total_price,

        -- Payment, printing and membership.
        {{ stg_text('payment_type', ['-', 'null', 'none', 'n/a']) }} as payment_type,
        {{ stg_text('print_count', ['-', 'null', 'none', 'n/a']) }} as print_count,
        {{ stg_text('is_member', ['-', 'null', 'none', 'n/a']) }} as is_member,

        -- Product batch relationship.
        {{ stg_text('batch_id', ['-', 'null', 'none', 'n/a']) }} as batch_id,

        -- Individual shift attributes.
        {{ stg_text('shift_date', ['-', 'null', 'none', 'n/a', '0000-00-00']) }} as shift_date,
        {{ stg_text('shift_period', ['-', 'null', 'none', 'n/a']) }} as shift_period,
        {{ stg_text('shift_cashier_code', []) }} as shift_cashier_code,

        -- Price tier number.
        {{ stg_text('price_tier_number', ['-', 'null', 'none', 'n/a']) }} as price_tier_number
    from {{ source('raw', 'sales_line') }}
)

select
    {{ stg_integer('sales_line_id', 'UInt32', positive=true) }} as sales_invoice_line_id,
    CAST(source_dataset AS LowCardinality(String)) as dataset_name,
    {{ stg_integer('source_row_number', 'UInt32', positive=true) }} as dataset_row_number,
    {{ stg_integer('invoice_id', 'UInt32', positive=true) }} as sales_invoice_id,
    {{ stg_integer('product_id', 'UInt32', positive=true) }} as product_id,
    {{ stg_integer('unit_id', 'UInt32', positive=true) }} as unit_id,
    {{ stg_integer('cashier_id', 'UInt32', positive=true) }} as cashier_id,

    -- Sale time and original shift designation.
    {{ stg_timestamp('sold_at', 'DateTime64(6)') }} as sold_at,
    CAST(shift AS Nullable(String)) as shift_label,

    -- Product and batch descriptions.
    CAST(drug_name AS String) as product_name,
    CAST(manufacturer AS LowCardinality(Nullable(String))) as manufacturer_name,
    CAST(drug_class AS LowCardinality(Nullable(String))) as drug_class_name,
    CAST(category AS LowCardinality(Nullable(String))) as category_name,
    CAST(batch_and_expiry_date AS Nullable(String)) as product_batch_label,

    -- Quantities, pricing, discounts, fees and tax.
    {{ stg_decimal('quantity', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as sold_quantity,
    {{ stg_decimal('unit_price', 'Decimal(18, 6)', precision=18, scale=6, percentage=false) }} as unit_price,
    CAST(price_tier AS LowCardinality(Nullable(String))) as price_tier_label,
    {{ stg_decimal('discount_pct', 'Nullable(Decimal(9, 4))', precision=9, scale=4, percentage=true) }} as discount_percentage,
    {{ stg_decimal('discount_amount', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as discount_amount,
    {{ stg_decimal('service_fee', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as service_fee_amount,
    {{ stg_decimal('packaging_fee', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as packaging_fee_amount,
    {{ stg_decimal('subtotal', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as subtotal_amount,
    {{ stg_decimal('invoice_discount_pct', 'Nullable(Decimal(9, 4))', precision=9, scale=4, percentage=true) }} as invoice_discount_percentage,
    {{ stg_decimal('promo_discount_pct', 'Nullable(Decimal(9, 4))', precision=9, scale=4, percentage=true) }} as promotional_discount_percentage,
    {{ stg_decimal('tax_pct', 'Nullable(Decimal(9, 4))', precision=9, scale=4, percentage=true) }} as tax_percentage,
    {{ stg_decimal('additional_fee', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as additional_fee_amount,
    {{ stg_decimal('total_price', 'Nullable(Decimal(18, 6))', precision=18, scale=6, percentage=false) }} as total_amount,

    -- Payment, printing and membership.
    {{ stg_domain('payment_type', 'LowCardinality(Nullable(String))', ['TUNAI', 'KARTU', 'KREDIT']) }} as payment_method,
    {{ stg_integer('print_count', 'Nullable(UInt16)', positive=false) }} as document_print_count,
    {{ stg_domain('is_member', 'LowCardinality(Nullable(String))', ['NON MEMBER', 'MEMBER']) }} as membership_status,

    -- Product batch relationship.
    {{ stg_integer('batch_id', 'Nullable(UInt32)', positive=true) }} as product_batch_id,

    -- Individual shift attributes.
    {{ stg_date('shift_date', 'Nullable(Date32)') }} as shift_date,
    {{ stg_domain('shift_period', 'LowCardinality(Nullable(String))', ['PAGI', 'SORE']) }} as shift_period,
    CAST(shift_cashier_code AS Nullable(String)) as shift_cashier_code,

    -- Price tier number.
    {{ stg_integer('price_tier_number', 'Nullable(UInt8)', positive=true) }} as price_tier_number
from cleaned
