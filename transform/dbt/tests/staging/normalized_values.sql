-- =============================================================================
-- DATA QUALITY: Normalized values
-- =============================================================================
-- Read every projection, including optional numeric fields, so malformed values fail the build.

-- Check: stg_manufacturers.
select 'stg_manufacturers' as model_name,
    countIf(not isValidUTF8(toString(`manufacturer_id`))
        or not isValidUTF8(toString(`manufacturer_name`))
        or (`manufacturer_name` is not null and (empty(`manufacturer_name`) or match(`manufacturer_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_manufacturers') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_drug_classes.
select 'stg_drug_classes' as model_name,
    countIf(not isValidUTF8(toString(`drug_class_id`))
        or not isValidUTF8(toString(`drug_class_name`))
        or (`drug_class_name` is not null and (empty(`drug_class_name`) or match(`drug_class_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_drug_classes') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_categories.
select 'stg_categories' as model_name,
    countIf(not isValidUTF8(toString(`category_id`))
        or not isValidUTF8(toString(`category_name`))
        or (`category_name` is not null and (empty(`category_name`) or match(`category_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_categories') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_products.
select 'stg_products' as model_name,
    countIf(not isValidUTF8(toString(`product_id`))
        or not isValidUTF8(toString(`product_code`))
        or (`product_code` is not null and (empty(`product_code`) or match(`product_code`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`product_name`))
        or (`product_name` is not null and (empty(`product_name`) or match(`product_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`manufacturer_id`))
        or not isValidUTF8(toString(`drug_class_id`))
        or not isValidUTF8(toString(`category_id`))) as invalid_rows
from {{ ref('stg_products') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_warehouses.
select 'stg_warehouses' as model_name,
    countIf(not isValidUTF8(toString(`warehouse_id`))
        or not isValidUTF8(toString(`warehouse_name`))
        or (`warehouse_name` is not null and (empty(`warehouse_name`) or match(`warehouse_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_warehouses') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_units.
select 'stg_units' as model_name,
    countIf(not isValidUTF8(toString(`unit_id`))
        or not isValidUTF8(toString(`unit_code`))
        or (`unit_code` is not null and (empty(`unit_code`) or match(`unit_code`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_units') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_cashiers.
select 'stg_cashiers' as model_name,
    countIf(not isValidUTF8(toString(`cashier_id`))
        or not isValidUTF8(toString(`cashier_code`))
        or (`cashier_code` is not null and (empty(`cashier_code`) or match(`cashier_code`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_cashiers') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_sales_invoices.
select 'stg_sales_invoices' as model_name,
    countIf(not isValidUTF8(toString(`sales_invoice_id`))
        or not isValidUTF8(toString(`sales_invoice_number`))
        or (`sales_invoice_number` is not null and (empty(`sales_invoice_number`) or match(`sales_invoice_number`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_sales_invoices') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_product_batches.
select 'stg_product_batches' as model_name,
    countIf(not isValidUTF8(toString(`product_batch_id`))
        or not isValidUTF8(toString(`product_id`))
        or not isValidUTF8(toString(`product_batch_number`))
        or (`product_batch_number` is not null and (empty(`product_batch_number`) or match(`product_batch_number`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`expiration_date`))) as invalid_rows
from {{ ref('stg_product_batches') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_sales_invoice_lines.
select 'stg_sales_invoice_lines' as model_name,
    countIf(not isValidUTF8(toString(`sales_invoice_line_id`))
        or not isValidUTF8(toString(`dataset_name`))
        or (`dataset_name` is not null and (empty(`dataset_name`) or match(`dataset_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`dataset_row_number`))
        or not isValidUTF8(toString(`sales_invoice_id`))
        or not isValidUTF8(toString(`product_id`))
        or not isValidUTF8(toString(`unit_id`))
        or not isValidUTF8(toString(`cashier_id`))
        or not isValidUTF8(toString(`sold_at`))
        or not isValidUTF8(toString(`shift_label`))
        or (`shift_label` is not null and (empty(`shift_label`) or match(`shift_label`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`product_name`))
        or (`product_name` is not null and (empty(`product_name`) or match(`product_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`manufacturer_name`))
        or (`manufacturer_name` is not null and (empty(`manufacturer_name`) or match(`manufacturer_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`drug_class_name`))
        or (`drug_class_name` is not null and (empty(`drug_class_name`) or match(`drug_class_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`category_name`))
        or (`category_name` is not null and (empty(`category_name`) or match(`category_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`product_batch_label`))
        or (`product_batch_label` is not null and (empty(`product_batch_label`) or match(`product_batch_label`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`sold_quantity`))
        or not isValidUTF8(toString(`unit_price`))
        or not isValidUTF8(toString(`price_tier_label`))
        or (`price_tier_label` is not null and (empty(`price_tier_label`) or match(`price_tier_label`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`discount_percentage`))
        or not isValidUTF8(toString(`discount_amount`))
        or not isValidUTF8(toString(`service_fee_amount`))
        or not isValidUTF8(toString(`packaging_fee_amount`))
        or not isValidUTF8(toString(`subtotal_amount`))
        or not isValidUTF8(toString(`invoice_discount_percentage`))
        or not isValidUTF8(toString(`promotional_discount_percentage`))
        or not isValidUTF8(toString(`tax_percentage`))
        or not isValidUTF8(toString(`additional_fee_amount`))
        or not isValidUTF8(toString(`total_amount`))
        or not isValidUTF8(toString(`payment_method`))
        or (`payment_method` is not null and (empty(`payment_method`) or match(`payment_method`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`document_print_count`))
        or not isValidUTF8(toString(`membership_status`))
        or (`membership_status` is not null and (empty(`membership_status`) or match(`membership_status`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`product_batch_id`))
        or not isValidUTF8(toString(`shift_date`))
        or not isValidUTF8(toString(`shift_period`))
        or (`shift_period` is not null and (empty(`shift_period`) or match(`shift_period`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`shift_cashier_code`))
        or (`shift_cashier_code` is not null and (empty(`shift_cashier_code`) or match(`shift_cashier_code`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`price_tier_number`))) as invalid_rows
from {{ ref('stg_sales_invoice_lines') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_inventory_documents.
select 'stg_inventory_documents' as model_name,
    countIf(not isValidUTF8(toString(`inventory_document_id`))
        or not isValidUTF8(toString(`inventory_document_number`))
        or (`inventory_document_number` is not null and (empty(`inventory_document_number`) or match(`inventory_document_number`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_inventory_documents') }}

-- Return only failing groups.
having invalid_rows > 0
union all

-- Check: stg_inventory_movements.
select 'stg_inventory_movements' as model_name,
    countIf(not isValidUTF8(toString(`inventory_movement_id`))
        or not isValidUTF8(toString(`dataset_name`))
        or (`dataset_name` is not null and (empty(`dataset_name`) or match(`dataset_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`dataset_row_number`))
        or not isValidUTF8(toString(`inventory_document_id`))
        or not isValidUTF8(toString(`product_id`))
        or not isValidUTF8(toString(`warehouse_id`))
        or not isValidUTF8(toString(`movement_at`))
        or not isValidUTF8(toString(`product_name`))
        or (`product_name` is not null and (empty(`product_name`) or match(`product_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`drug_class_name`))
        or (`drug_class_name` is not null and (empty(`drug_class_name`) or match(`drug_class_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`category_name`))
        or (`category_name` is not null and (empty(`category_name`) or match(`category_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`consignment_status`))
        or (`consignment_status` is not null and (empty(`consignment_status`) or match(`consignment_status`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`product_status`))
        or (`product_status` is not null and (empty(`product_status`) or match(`product_status`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`transaction_description`))
        or (`transaction_description` is not null and (empty(`transaction_description`) or match(`transaction_description`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`opening_stock_quantity`))
        or not isValidUTF8(toString(`received_quantity`))
        or not isValidUTF8(toString(`issued_quantity`))
        or not isValidUTF8(toString(`closing_stock_quantity`))
        or not isValidUTF8(toString(`opening_stock_unit_id`))
        or not isValidUTF8(toString(`received_unit_id`))
        or not isValidUTF8(toString(`issued_unit_id`))
        or not isValidUTF8(toString(`closing_stock_unit_id`))
        or not isValidUTF8(toString(`transaction_type`))
        or (`transaction_type` is not null and (empty(`transaction_type`) or match(`transaction_type`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`supplier_name`))
        or (`supplier_name` is not null and (empty(`supplier_name`) or match(`supplier_name`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`referenced_sales_invoice_number`))
        or (`referenced_sales_invoice_number` is not null and (empty(`referenced_sales_invoice_number`) or match(`referenced_sales_invoice_number`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))
        or not isValidUTF8(toString(`patient_code`))
        or (`patient_code` is not null and (empty(`patient_code`) or match(`patient_code`, '^[\\s\\x{00A0}]|[\\s\\x{00A0}]$')))) as invalid_rows
from {{ ref('stg_inventory_movements') }}

-- Return only failing groups.
having invalid_rows > 0
