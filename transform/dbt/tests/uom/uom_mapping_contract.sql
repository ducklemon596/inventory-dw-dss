-- Validate all published rows; a candidate number never implies approval.
select mapping_version, product_id, sales_unit
from {{ ref('uom_conversion_mapping') }}
where trimBoth(product_id) != product_id or product_id = ''
    or trimBoth(sales_unit) != sales_unit or sales_unit = ''
    or trimBoth(stock_unit) != stock_unit or stock_unit = ''
    or tier not in ('A', 'B', 'C')
    or approval_status != multiIf(tier = 'A', 'approved', tier = 'B', 'candidate', 'quarantined')
    or (approval_status = 'approved' and (isNull(factor_approved) or factor_approved <= 0))
    or (approval_status != 'approved' and isNotNull(factor_approved))
    or (isNotNull(factor_candidate) and factor_candidate <= 0)
    or (approval_status = 'approved' and isNotNull(factor_candidate))
    or n_supporting_invoices = 0
    or share_at_mode < 0 or share_at_mode > 1
    or trimBoth(evidence_source) = ''
