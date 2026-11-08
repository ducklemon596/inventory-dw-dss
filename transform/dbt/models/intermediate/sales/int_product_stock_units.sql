-- REFERENCE: One observed product / export with a verified recorded stock unit
-- No sales warehouse is inferred. Unit agreement must hold across all warehouses.
with observations as (
    select
        dataset_name,
        product_id,
        uniqExact(closing_stock_unit_id) as recorded_stock_unit_count,
        countIf(opening_stock_unit_id != closing_stock_unit_id
                or received_unit_id != closing_stock_unit_id
                or issued_unit_id != closing_stock_unit_id) as inconsistent_unit_movement_count,
        if(recorded_stock_unit_count = 1 and inconsistent_unit_movement_count = 0,
           toNullable(min(closing_stock_unit_id)), null) as stock_unit_id
    from {{ ref('stg_inventory_movements') }}
    group by dataset_name, product_id
)
select
    observations.dataset_name as dataset_name,
    observations.product_id as product_id,
    products.product_code as product_code,
    observations.stock_unit_id as stock_unit_id,
    units.unit_code as stock_unit_code,
    observations.recorded_stock_unit_count as recorded_stock_unit_count,
    observations.inconsistent_unit_movement_count as inconsistent_unit_movement_count
from observations
left join {{ ref('stg_products') }} as products on observations.product_id = products.product_id
left join {{ ref('stg_units') }} as units on observations.stock_unit_id = units.unit_id
