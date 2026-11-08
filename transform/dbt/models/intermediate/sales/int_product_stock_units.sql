-- REFERENCE: One observed product / export with a verified recorded stock unit
-- No sales warehouse is inferred. Unit agreement must hold across all warehouses.
WITH observations AS (
    SELECT
        dataset_name,
        product_id,
        uniqExact(closing_stock_unit_id) AS recorded_stock_unit_count,
        countIf(
            opening_stock_unit_id != closing_stock_unit_id
            OR received_unit_id != closing_stock_unit_id
            OR issued_unit_id != closing_stock_unit_id
        ) AS inconsistent_unit_movement_count,
        -- Ambiguous or internally inconsistent units leave conversion evidence unresolved.
        if(
            recorded_stock_unit_count = 1 AND inconsistent_unit_movement_count = 0,
            toNullable(min(closing_stock_unit_id)),
            NULL
        ) AS stock_unit_id
    FROM {{ ref('stg_inventory_movements') }}
    GROUP BY dataset_name, product_id
)
SELECT
    observations.dataset_name AS dataset_name,
    observations.product_id AS product_id,
    products.product_code AS product_code,
    observations.stock_unit_id AS stock_unit_id,
    units.unit_code AS stock_unit_code,
    observations.recorded_stock_unit_count AS recorded_stock_unit_count,
    observations.inconsistent_unit_movement_count AS inconsistent_unit_movement_count
FROM observations
LEFT JOIN {{ ref('stg_products') }} AS products
    ON observations.product_id = products.product_id
LEFT JOIN {{ ref('stg_units') }} AS units
    ON observations.stock_unit_id = units.unit_id
