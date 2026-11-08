-- FACT: One recorded inventory movement; quantities and lineage remain unchanged
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, warehouse_id, movement_date, dataset_row_number)'
) }}

-- Discontinuity deltas remain diagnostic; recorded_delta_qty is the only flow effect.
SELECT
    inventory_movement_id,
    dataset_name,
    dataset_row_number,
    inventory_document_id,
    product_id,
    warehouse_id,
    movement_at,
    product_name,
    drug_class_name,
    category_name,
    consignment_status,
    product_status,
    transaction_description,
    opening_stock_quantity,
    received_quantity,
    issued_quantity,
    closing_stock_quantity,
    opening_stock_unit_id,
    received_unit_id,
    issued_unit_id,
    closing_stock_unit_id,
    transaction_type,
    supplier_name,
    referenced_sales_invoice_number,
    patient_code,
    movement_date,
    recorded_delta_qty,
    segment_id,
    segment_start_sequence,
    is_ledger_start,
    is_discontinuity,
    is_continuous,
    continuity_delta_qty,
    has_negative_opening_stock,
    has_negative_closing_stock,
    is_unknown_movement
FROM {{ ref('int_inventory_segments') }}
