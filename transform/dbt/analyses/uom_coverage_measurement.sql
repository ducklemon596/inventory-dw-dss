-- Coverage is measured in each SKU's original unit, never by pooling Box and Tab.
-- Row and pair/SKU coverage are separate counts; these quantities are not stock totals.
select
    *,
    if(absolute_sales_quantity = 0, CAST(null AS Nullable(Decimal(76, 6))),
       divideDecimal(toDecimal256(covered_absolute_sales_quantity, 6) * toDecimal256(100, 0),
                     toDecimal256(if(absolute_sales_quantity = 0, 1, absolute_sales_quantity), 6), 6)
    ) as original_unit_quantity_coverage_percent
from {{ ref('int_sales_uom_coverage') }}
order by dataset_name, product_code, unit_code
