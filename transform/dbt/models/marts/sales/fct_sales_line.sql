-- One original sales line; approved quantities and unresolved NULLs pass through unchanged.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, sold_date, sales_invoice_line_id)'
) }}

SELECT
    sales_invoice_line_id,
    dataset_name,
    dataset_row_number,
    sales_invoice_id,
    sales_invoice_number,
    product_id,
    product_code,
    unit_id,
    unit_code,
    cashier_id,
    cashier_code,

    sold_at,
    sold_date,
    shift_label,
    shift_date,
    shift_period,
    shift_cashier_code,
    product_name,
    manufacturer_name,
    drug_class_name,
    category_name,

    product_batch_id,
    product_batch_label,
    product_batch_number,
    expiration_date,

    sold_quantity,
    unit_price,
    price_tier_label,
    price_tier_number,
    discount_percentage,
    discount_amount,
    service_fee_amount,
    packaging_fee_amount,
    subtotal_amount,
    invoice_discount_percentage,
    promotional_discount_percentage,
    tax_percentage,
    additional_fee_amount,
    total_amount,
    payment_method,
    document_print_count,
    membership_status,

    verified_stock_unit_id,
    verified_stock_unit_code,
    mapping_tier,
    mapping_approval_status,
    approved_conversion_factor,
    mapping_supporting_invoice_count,
    mapping_share_at_mode,
    mapping_price_ratio,
    mapping_price_check_within_15pct,
    mapping_evidence_source,
    mapping_stock_unit_code,

    mapping_version,

    conversion_status,
    applied_conversion_factor,
    stock_unit_qty
FROM {{ ref('int_sales_quantity_converted') }}
