-- INTERMEDIATE: Recorded sales lines with business identifiers
-- Grain: one source sales invoice line. Approved rules: I-01 and I-03.
-- Lookup joins preserve optional batches and never define sale eligibility.

with sales_lines as (
    select * from {{ ref('stg_sales_invoice_lines') }}
),
invoices as (
    select * from {{ ref('stg_sales_invoices') }}
),
products as (
    select product_id, product_code from {{ ref('stg_products') }}
),
units as (
    select * from {{ ref('stg_units') }}
),
cashiers as (
    select * from {{ ref('stg_cashiers') }}
),
batches as (
    select * from {{ ref('stg_product_batches') }}
)

-- Preserve transaction observations; add codes and batch attributes.
select
    -- Source identifiers and business codes.
    sales_lines.sales_invoice_line_id as sales_invoice_line_id,
    sales_lines.dataset_name as dataset_name,
    sales_lines.dataset_row_number as dataset_row_number,
    sales_lines.sales_invoice_id as sales_invoice_id,
    invoices.sales_invoice_number as sales_invoice_number,
    sales_lines.product_id as product_id,
    products.product_code as product_code,
    sales_lines.unit_id as unit_id,
    units.unit_code as unit_code,
    sales_lines.cashier_id as cashier_id,
    cashiers.cashier_code as cashier_code,

    -- Line-level event time, shift and historical descriptions.
    sales_lines.sold_at as sold_at,
    toDate32(sales_lines.sold_at) as sold_date,
    sales_lines.shift_label as shift_label,
    sales_lines.shift_date as shift_date,
    sales_lines.shift_period as shift_period,
    sales_lines.shift_cashier_code as shift_cashier_code,
    sales_lines.product_name as product_name,
    sales_lines.manufacturer_name as manufacturer_name,
    sales_lines.drug_class_name as drug_class_name,
    sales_lines.category_name as category_name,
    sales_lines.product_batch_id as product_batch_id,
    sales_lines.product_batch_label as product_batch_label,
    batches.product_batch_number as product_batch_number,
    batches.expiration_date as expiration_date,

    -- Recorded quantities, amounts and percentages retain their line scope.
    sales_lines.sold_quantity as sold_quantity,
    sales_lines.unit_price as unit_price,
    sales_lines.price_tier_label as price_tier_label,
    sales_lines.price_tier_number as price_tier_number,
    sales_lines.discount_percentage as discount_percentage,
    sales_lines.discount_amount as discount_amount,
    sales_lines.service_fee_amount as service_fee_amount,
    sales_lines.packaging_fee_amount as packaging_fee_amount,
    sales_lines.subtotal_amount as subtotal_amount,
    sales_lines.invoice_discount_percentage as invoice_discount_percentage,
    sales_lines.promotional_discount_percentage as promotional_discount_percentage,
    sales_lines.tax_percentage as tax_percentage,
    sales_lines.additional_fee_amount as additional_fee_amount,
    sales_lines.total_amount as total_amount,
    sales_lines.payment_method as payment_method,
    sales_lines.document_print_count as document_print_count,
    sales_lines.membership_status as membership_status
from sales_lines
left join invoices on sales_lines.sales_invoice_id = invoices.sales_invoice_id
left join products on sales_lines.product_id = products.product_id
left join units on sales_lines.unit_id = units.unit_id
left join cashiers on sales_lines.cashier_id = cashiers.cashier_id
left join batches
    on sales_lines.product_batch_id = batches.product_batch_id
    and sales_lines.product_id = batches.product_id
