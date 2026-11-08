-- Keep every recorded sales line, including lines without a batch.
-- Product catalog codes enrich the line; transaction-recorded names and amounts remain authoritative.

WITH sales_lines AS (
    SELECT *
    FROM {{ ref('stg_sales_invoice_lines') }}
),

invoices AS (
    SELECT *
    FROM {{ ref('stg_sales_invoices') }}
),

products AS (
    SELECT
        product_id,
        product_code
    FROM {{ ref('stg_products') }}
),

units AS (
    SELECT *
    FROM {{ ref('stg_units') }}
),

cashiers AS (
    SELECT *
    FROM {{ ref('stg_cashiers') }}
),

batches AS (
    SELECT *
    FROM {{ ref('stg_product_batches') }}
)

SELECT
    -- Source identifiers and business codes.
    sales_lines.sales_invoice_line_id AS sales_invoice_line_id,
    sales_lines.dataset_name AS dataset_name,
    sales_lines.dataset_row_number AS dataset_row_number,
    sales_lines.sales_invoice_id AS sales_invoice_id,
    invoices.sales_invoice_number AS sales_invoice_number,
    sales_lines.product_id AS product_id,
    products.product_code AS product_code,
    sales_lines.unit_id AS unit_id,
    units.unit_code AS unit_code,
    sales_lines.cashier_id AS cashier_id,
    cashiers.cashier_code AS cashier_code,

    -- Line-level event time, shift and historical descriptions.
    sales_lines.sold_at AS sold_at,
    toDate32(sales_lines.sold_at) AS sold_date,
    sales_lines.shift_label AS shift_label,
    sales_lines.shift_date AS shift_date,
    sales_lines.shift_period AS shift_period,
    sales_lines.shift_cashier_code AS shift_cashier_code,
    sales_lines.product_name AS product_name,
    sales_lines.manufacturer_name AS manufacturer_name,
    sales_lines.drug_class_name AS drug_class_name,
    sales_lines.category_name AS category_name,
    sales_lines.product_batch_id AS product_batch_id,
    sales_lines.product_batch_label AS product_batch_label,
    batches.product_batch_number AS product_batch_number,
    batches.expiration_date AS expiration_date,

    -- Recorded quantities, amounts and percentages retain their line scope.
    sales_lines.sold_quantity AS sold_quantity,
    sales_lines.unit_price AS unit_price,
    sales_lines.price_tier_label AS price_tier_label,
    sales_lines.price_tier_number AS price_tier_number,
    sales_lines.discount_percentage AS discount_percentage,
    sales_lines.discount_amount AS discount_amount,
    sales_lines.service_fee_amount AS service_fee_amount,
    sales_lines.packaging_fee_amount AS packaging_fee_amount,
    sales_lines.subtotal_amount AS subtotal_amount,
    sales_lines.invoice_discount_percentage AS invoice_discount_percentage,
    sales_lines.promotional_discount_percentage AS promotional_discount_percentage,
    sales_lines.tax_percentage AS tax_percentage,
    sales_lines.additional_fee_amount AS additional_fee_amount,
    sales_lines.total_amount AS total_amount,
    sales_lines.payment_method AS payment_method,
    sales_lines.document_print_count AS document_print_count,
    sales_lines.membership_status AS membership_status
FROM sales_lines
LEFT JOIN invoices
    ON sales_lines.sales_invoice_id = invoices.sales_invoice_id
LEFT JOIN products
    ON sales_lines.product_id = products.product_id
LEFT JOIN units
    ON sales_lines.unit_id = units.unit_id
LEFT JOIN cashiers
    ON sales_lines.cashier_id = cashiers.cashier_id
LEFT JOIN batches
    ON sales_lines.product_batch_id = batches.product_batch_id
    AND sales_lines.product_id = batches.product_id
