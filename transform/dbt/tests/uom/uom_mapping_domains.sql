-- Match exact business labels; never normalize or join DrugCode to a numeric ID.
select mapping.mapping_version, mapping.product_id, mapping.sales_unit
from {{ ref('uom_conversion_mapping') }} as mapping
left join {{ ref('stg_products') }} as product on mapping.product_id = product.product_code
left join {{ ref('stg_units') }} as sales_unit on mapping.sales_unit = sales_unit.unit_code
left join {{ ref('stg_units') }} as stock_unit on mapping.stock_unit = stock_unit.unit_code
where product.product_id is null or sales_unit.unit_id is null or stock_unit.unit_id is null
settings join_use_nulls = 1
