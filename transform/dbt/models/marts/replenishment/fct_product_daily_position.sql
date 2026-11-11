-- FACT: Pharmacy-level daily position per product, split by dispensary and storeroom stock
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, position_date)'
) }}

-- Sales happen at the dispensary; other warehouses replenish it through transfers.
{% set dispensary_id = var('replenishment_dispensary_warehouse_id') %}

WITH positions AS (
    SELECT *
    FROM {{ ref('int_inventory_daily_position') }}
),

-- A warehouse without a ledger yet holds no stock, so it contributes zero before its first movement.
product_days AS (
    SELECT
        dataset_name,
        product_id,
        position_date,
        any(stock_unit_id) AS stock_unit_id,
        anyIf(consignment_status, warehouse_id = {{ dispensary_id }}) AS dispensary_consignment_status,
        any(consignment_status) AS any_consignment_status,
        sumIf(on_hand_qty, warehouse_id = {{ dispensary_id }}) AS dispensary_on_hand_qty,
        sumIf(on_hand_qty, warehouse_id != {{ dispensary_id }}) AS storeroom_on_hand_qty,
        sum(sold_qty) AS sold_qty,
        sum(customer_return_qty) AS customer_return_qty,
        sum(purchase_received_qty) AS purchase_received_qty,
        sumIf(transfer_in_qty, warehouse_id = {{ dispensary_id }}) AS transfer_to_dispensary_qty,
        sum(adjustment_qty) AS adjustment_qty,
        sum(balance_gap_qty) AS balance_gap_qty,
        max(has_purchase_receipt) AS has_purchase_receipt,
        max(has_stocktake) AS has_stocktake,
        sum(movement_count) AS movement_count,
        countIf(warehouse_id = {{ dispensary_id }}) AS dispensary_ledger_count
    FROM positions
    GROUP BY
        dataset_name,
        product_id,
        position_date
),

-- Sales value per product-day; quantities come from the ledger because sales units can differ from stock units.
sales_value AS (
    SELECT
        dataset_name,
        product_id,
        sold_date,
        sum(subtotal_amount) AS sales_amount,
        count() AS sales_line_count
    FROM {{ ref('fct_sales_line') }}
    GROUP BY
        dataset_name,
        product_id,
        sold_date
)

SELECT
    product_days.dataset_name AS dataset_name,
    product_days.product_id AS product_id,
    product_days.position_date AS position_date,
    product_days.stock_unit_id AS stock_unit_id,
    toUInt8(ifNull(
        coalesce(product_days.dispensary_consignment_status, product_days.any_consignment_status) = 'KONSINYASI',
        FALSE
    )) AS is_consignment,

    -- Recorded balances in the product's stock unit; negative values are kept for diagnostics.
    product_days.dispensary_on_hand_qty AS dispensary_on_hand_qty,
    product_days.storeroom_on_hand_qty AS storeroom_on_hand_qty,
    product_days.dispensary_on_hand_qty + product_days.storeroom_on_hand_qty AS pharmacy_on_hand_qty,

    -- Daily flows in the product's stock unit.
    product_days.sold_qty AS sold_qty,
    product_days.customer_return_qty AS customer_return_qty,
    product_days.purchase_received_qty AS purchase_received_qty,
    product_days.transfer_to_dispensary_qty AS transfer_to_dispensary_qty,
    product_days.adjustment_qty AS adjustment_qty,
    product_days.balance_gap_qty AS balance_gap_qty,
    toDecimal64(ifNull(sales_value.sales_amount, 0), 6) AS sales_amount,
    toUInt32(ifNull(sales_value.sales_line_count, 0)) AS sales_line_count,

    -- Status flags. Stockout is judged at the point of sale, which is where demand is lost.
    toUInt8(product_days.dispensary_ledger_count > 0) AS has_dispensary_ledger,
    toUInt8(product_days.dispensary_on_hand_qty <= 0) AS is_dispensary_stockout,
    toUInt8(product_days.dispensary_on_hand_qty + product_days.storeroom_on_hand_qty <= 0) AS is_pharmacy_stockout,
    toUInt8(product_days.dispensary_on_hand_qty < 0 OR product_days.storeroom_on_hand_qty < 0) AS has_negative_on_hand,
    product_days.has_purchase_receipt AS has_purchase_receipt,
    product_days.has_stocktake AS has_stocktake,
    toUInt32(product_days.movement_count) AS movement_count
FROM product_days
LEFT JOIN sales_value
    ON product_days.dataset_name = sales_value.dataset_name
    AND product_days.product_id = sales_value.product_id
    AND product_days.position_date = sales_value.sold_date
