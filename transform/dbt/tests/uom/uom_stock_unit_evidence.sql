select dataset_name, product_id
from {{ ref('int_product_stock_units') }}
where stock_unit_id is null or stock_unit_code is null or product_code is null
    or recorded_stock_unit_count != 1 or inconsistent_unit_movement_count != 0
