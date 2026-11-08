-- INTERMEDIATE: Recorded inventory movements with business identifiers
-- Grain: one source inventory movement. Approved rules: I-02 and I-03.
-- No type-based sign mapping, return matching, filtering or balance repair.

with movements as (
    select * from {{ ref('stg_inventory_movements') }}
),
documents as (
    select * from {{ ref('stg_inventory_documents') }}
),
products as (
    select product_id, product_code from {{ ref('stg_products') }}
),
warehouses as (
    select * from {{ ref('stg_warehouses') }}
),
units as (
    select * from {{ ref('stg_units') }}
)

-- Preserve source observations and expose their recorded quantity effect.
select
    -- Source identifiers and business codes.
    movements.inventory_movement_id as inventory_movement_id,
    movements.dataset_name as dataset_name,
    movements.dataset_row_number as dataset_row_number,
    movements.inventory_document_id as inventory_document_id,
    documents.inventory_document_number as inventory_document_number,
    movements.product_id as product_id,
    products.product_code as product_code,
    movements.warehouse_id as warehouse_id,
    warehouses.warehouse_name as warehouse_name,
    movements.movement_at as movement_at,
    toDate32(movements.movement_at) as movement_date,

    -- Historical transaction attributes; classifications remain unchanged.
    movements.product_name as product_name,
    movements.drug_class_name as drug_class_name,
    movements.category_name as category_name,
    movements.consignment_status as consignment_status,
    movements.product_status as product_status,
    movements.transaction_type as transaction_type,
    movements.transaction_description as transaction_description,
    movements.supplier_name as supplier_name,
    movements.referenced_sales_invoice_number as referenced_sales_invoice_number,
    movements.patient_code as patient_code,

    -- Keep all four quantities and their original units for reconciliation.
    movements.opening_stock_quantity as opening_stock_quantity,
    movements.received_quantity as received_quantity,
    movements.issued_quantity as issued_quantity,
    movements.closing_stock_quantity as closing_stock_quantity,
    movements.opening_stock_unit_id as opening_stock_unit_id,
    opening_units.unit_code as opening_stock_unit_code,
    movements.received_unit_id as received_unit_id,
    received_units.unit_code as received_unit_code,
    movements.issued_unit_id as issued_unit_id,
    issued_units.unit_code as issued_unit_code,
    movements.closing_stock_unit_id as closing_stock_unit_id,
    closing_units.unit_code as closing_stock_unit_code,

    -- Unit equality is asserted by a dbt test; no implicit conversion applies.
    movements.received_quantity - movements.issued_quantity as recorded_delta_qty,

    -- Diagnostic flags preserve the underlying rows and negative observations.
    movements.opening_stock_quantity < 0 as has_negative_opening_stock,
    movements.closing_stock_quantity < 0 as has_negative_closing_stock,
    CAST(ifNull(movements.transaction_type = 'UNKNOWN', false) AS UInt8) as is_unknown_movement
from movements
left join documents on movements.inventory_document_id = documents.inventory_document_id
left join products on movements.product_id = products.product_id
left join warehouses on movements.warehouse_id = warehouses.warehouse_id
left join units as opening_units on movements.opening_stock_unit_id = opening_units.unit_id
left join units as received_units on movements.received_unit_id = received_units.unit_id
left join units as issued_units on movements.issued_unit_id = issued_units.unit_id
left join units as closing_units on movements.closing_stock_unit_id = closing_units.unit_id
