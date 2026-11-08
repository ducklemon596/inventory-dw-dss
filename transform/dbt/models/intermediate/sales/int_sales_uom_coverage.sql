-- COVERAGE: Export / product / original sales unit / mapping version
-- Absolute quantities remain in one product's original unit; never pool Box/Tab/etc.
select
    dataset_name,
    product_id,
    product_code,
    unit_id,
    unit_code,
    mapping_version,
    any(verified_stock_unit_code) as verified_stock_unit_code,
    count() as sales_line_count,
    countIf(conversion_status = 'identity') as identity_line_count,
    countIf(conversion_status = 'approved') as approved_line_count,
    countIf(conversion_status = 'candidate') as candidate_line_count,
    countIf(conversion_status = 'quarantined') as quarantined_line_count,
    countIf(conversion_status = 'unmapped') as unmapped_line_count,
    sum(abs(sold_quantity)) as absolute_sales_quantity,
    sumIf(abs(sold_quantity), conversion_status in ('identity', 'approved')) as covered_absolute_sales_quantity,
    sumIf(abs(sold_quantity), conversion_status not in ('identity', 'approved')) as unresolved_absolute_sales_quantity
from {{ ref('int_sales_quantity_converted') }}
group by dataset_name, product_id, product_code, unit_id, unit_code, mapping_version
