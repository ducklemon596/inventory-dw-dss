-- =============================================================================
-- DATA QUALITY: Source row counts
-- =============================================================================
-- Run on a stable raw snapshot: concurrent ingestion can invalidate count comparisons.
with reconciliation as (

-- Check: manufacturer.
select 'manufacturer' as source_table,
    (select count() from {{ source('raw', 'manufacturer') }}) as raw_rows,
    (select count() from {{ ref('stg_manufacturers') }}) as staging_rows
union all

-- Check: drug_class.
select 'drug_class' as source_table,
    (select count() from {{ source('raw', 'drug_class') }}) as raw_rows,
    (select count() from {{ ref('stg_drug_classes') }}) as staging_rows
union all

-- Check: category.
select 'category' as source_table,
    (select count() from {{ source('raw', 'category') }}) as raw_rows,
    (select count() from {{ ref('stg_categories') }}) as staging_rows
union all

-- Check: product.
select 'product' as source_table,
    (select count() from {{ source('raw', 'product') }}) as raw_rows,
    (select count() from {{ ref('stg_products') }}) as staging_rows
union all

-- Check: warehouse.
select 'warehouse' as source_table,
    (select count() from {{ source('raw', 'warehouse') }}) as raw_rows,
    (select count() from {{ ref('stg_warehouses') }}) as staging_rows
union all

-- Check: unit.
select 'unit' as source_table,
    (select count() from {{ source('raw', 'unit') }}) as raw_rows,
    (select count() from {{ ref('stg_units') }}) as staging_rows
union all

-- Check: cashier.
select 'cashier' as source_table,
    (select count() from {{ source('raw', 'cashier') }}) as raw_rows,
    (select count() from {{ ref('stg_cashiers') }}) as staging_rows
union all

-- Check: sales_invoice.
select 'sales_invoice' as source_table,
    (select count() from {{ source('raw', 'sales_invoice') }}) as raw_rows,
    (select count() from {{ ref('stg_sales_invoices') }}) as staging_rows
union all

-- Check: product_batch.
select 'product_batch' as source_table,
    (select count() from {{ source('raw', 'product_batch') }}) as raw_rows,
    (select count() from {{ ref('stg_product_batches') }}) as staging_rows
union all

-- Check: sales_line.
select 'sales_line' as source_table,
    (select count() from {{ source('raw', 'sales_line') }}) as raw_rows,
    (select count() from {{ ref('stg_sales_invoice_lines') }}) as staging_rows
union all

-- Check: inventory_document.
select 'inventory_document' as source_table,
    (select count() from {{ source('raw', 'inventory_document') }}) as raw_rows,
    (select count() from {{ ref('stg_inventory_documents') }}) as staging_rows
union all

-- Check: inventory_movement.
select 'inventory_movement' as source_table,
    (select count() from {{ source('raw', 'inventory_movement') }}) as raw_rows,
    (select count() from {{ ref('stg_inventory_movements') }}) as staging_rows
)
select * from reconciliation where raw_rows != staging_rows
