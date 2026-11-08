-- Aggregation is permitted only in a stable recorded stock unit per export-ledger.
select dataset_name, product_id, warehouse_id
from {{ ref('stg_inventory_movements') }}
group by dataset_name, product_id, warehouse_id
having uniqExact(opening_stock_unit_id) != 1
    or uniqExact(received_unit_id) != 1
    or uniqExact(issued_unit_id) != 1
    or uniqExact(closing_stock_unit_id) != 1
    or min(opening_stock_unit_id) != min(closing_stock_unit_id)
    or min(received_unit_id) != min(closing_stock_unit_id)
    or min(issued_unit_id) != min(closing_stock_unit_id)
