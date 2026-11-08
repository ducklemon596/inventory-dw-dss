-- Recorded receipts minus issues define the movement effect, including RETURN and UNKNOWN rows.
-- Keep source balances and descriptions so negative stock and gaps can be investigated.

WITH movements AS (
    SELECT *
    FROM {{ ref('stg_inventory_movements') }}
),

documents AS (
    SELECT *
    FROM {{ ref('stg_inventory_documents') }}
),

products AS (
    SELECT
        product_id,
        product_code
    FROM {{ ref('stg_products') }}
),

warehouses AS (
    SELECT *
    FROM {{ ref('stg_warehouses') }}
),

units AS (
    SELECT *
    FROM {{ ref('stg_units') }}
)

SELECT
    -- Source identifiers and business codes.
    movements.inventory_movement_id AS inventory_movement_id,
    movements.dataset_name AS dataset_name,
    movements.dataset_row_number AS dataset_row_number,
    movements.inventory_document_id AS inventory_document_id,
    documents.inventory_document_number AS inventory_document_number,
    movements.product_id AS product_id,
    products.product_code AS product_code,
    movements.warehouse_id AS warehouse_id,
    warehouses.warehouse_name AS warehouse_name,
    movements.movement_at AS movement_at,
    toDate32(movements.movement_at) AS movement_date,

    -- Historical transaction attributes; classifications remain unchanged.
    movements.product_name AS product_name,
    movements.drug_class_name AS drug_class_name,
    movements.category_name AS category_name,
    movements.consignment_status AS consignment_status,
    movements.product_status AS product_status,
    movements.transaction_type AS transaction_type,
    movements.transaction_description AS transaction_description,
    movements.supplier_name AS supplier_name,
    movements.referenced_sales_invoice_number AS referenced_sales_invoice_number,
    movements.patient_code AS patient_code,

    -- Keep all four quantities and their original units for reconciliation.
    movements.opening_stock_quantity AS opening_stock_quantity,
    movements.received_quantity AS received_quantity,
    movements.issued_quantity AS issued_quantity,
    movements.closing_stock_quantity AS closing_stock_quantity,
    movements.opening_stock_unit_id AS opening_stock_unit_id,
    opening_units.unit_code AS opening_stock_unit_code,
    movements.received_unit_id AS received_unit_id,
    received_units.unit_code AS received_unit_code,
    movements.issued_unit_id AS issued_unit_id,
    issued_units.unit_code AS issued_unit_code,
    movements.closing_stock_unit_id AS closing_stock_unit_id,
    closing_units.unit_code AS closing_stock_unit_code,

    -- Unit equality is asserted by a dbt test; no implicit conversion applies.
    movements.received_quantity - movements.issued_quantity AS recorded_delta_qty,

    -- Diagnostic flags preserve the underlying rows and negative observations.
    movements.opening_stock_quantity < 0 AS has_negative_opening_stock,
    movements.closing_stock_quantity < 0 AS has_negative_closing_stock,
    CAST(ifNull(movements.transaction_type = 'UNKNOWN', FALSE) AS UInt8) AS is_unknown_movement
FROM movements
LEFT JOIN documents
    ON movements.inventory_document_id = documents.inventory_document_id
LEFT JOIN products
    ON movements.product_id = products.product_id
LEFT JOIN warehouses
    ON movements.warehouse_id = warehouses.warehouse_id
LEFT JOIN units AS opening_units
    ON movements.opening_stock_unit_id = opening_units.unit_id
LEFT JOIN units AS received_units
    ON movements.received_unit_id = received_units.unit_id
LEFT JOIN units AS issued_units
    ON movements.issued_unit_id = issued_units.unit_id
LEFT JOIN units AS closing_units
    ON movements.closing_stock_unit_id = closing_units.unit_id
