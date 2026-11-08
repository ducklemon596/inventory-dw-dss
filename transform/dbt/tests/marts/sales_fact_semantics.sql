select sales_invoice_line_id
from {{ ref('fct_sales_line') }}
where sold_date != toDate32(sold_at)
    or mapping_version != {{ uom_mapping_version_literal() }}
    or conversion_status not in ('identity', 'approved', 'candidate', 'quarantined', 'unmapped')
    or (conversion_status in ('identity', 'approved')
        and (stock_unit_qty is null or applied_conversion_factor is null or verified_stock_unit_id = 0))
    or (conversion_status in ('candidate', 'quarantined', 'unmapped')
        and (stock_unit_qty is not null or applied_conversion_factor is not null))
    or (verified_stock_unit_id = 0
        and (verified_stock_unit_code is not null
            or applied_conversion_factor is not null
            or stock_unit_qty is not null))
