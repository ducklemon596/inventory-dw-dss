-- Check the selected reference independently of exposed factor/status metadata.
with mapping as (
    select * from {{ ref('uom_conversion_mapping') }}
    where mapping_version = {{ uom_mapping_version_literal() }}
)
select actual.sales_invoice_line_id
from {{ ref('int_sales_quantity_converted') }} as actual
left join mapping on actual.product_code = mapping.product_id and actual.unit_code = mapping.sales_unit
left join {{ ref('int_product_stock_units') }} as stocks
    on actual.dataset_name = stocks.dataset_name and actual.product_id = stocks.product_id
where actual.mapping_version != {{ uom_mapping_version_literal() }}
    or not isNotDistinctFrom(actual.verified_stock_unit_id, stocks.stock_unit_id)
    or not isNotDistinctFrom(actual.verified_stock_unit_code, stocks.stock_unit_code)
    or not isNotDistinctFrom(actual.approved_conversion_factor, mapping.factor_approved)
    or not isNotDistinctFrom(actual.mapping_tier, mapping.tier)
    or not isNotDistinctFrom(actual.mapping_approval_status, mapping.approval_status)
    or not isNotDistinctFrom(actual.mapping_evidence_source, mapping.evidence_source)
    or (actual.conversion_status = 'identity' and (
        isNull(stocks.stock_unit_id) or actual.unit_code != stocks.stock_unit_code
        or not isNotDistinctFrom(actual.stock_unit_qty, toDecimal128(actual.sold_quantity, 12))
        or not isNotDistinctFrom(actual.applied_conversion_factor, toDecimal64(1, 6))))
    or (actual.conversion_status = 'approved' and (
        mapping.approval_status != 'approved' or mapping.tier != 'A' or isNull(mapping.factor_approved)
        or mapping.factor_approved <= 0 or mapping.stock_unit != stocks.stock_unit_code
        or not isNotDistinctFrom(actual.stock_unit_qty,
            toDecimal128(actual.sold_quantity, 6) * toDecimal128(mapping.factor_approved, 6))
        or not isNotDistinctFrom(actual.applied_conversion_factor, mapping.factor_approved)))
    or (actual.conversion_status in ('candidate', 'quarantined', 'unmapped')
        and (isNotNull(actual.stock_unit_qty) or isNotNull(actual.applied_conversion_factor)))
    or (actual.conversion_status = 'candidate' and mapping.approval_status != 'candidate')
    or (actual.conversion_status = 'quarantined' and mapping.approval_status != 'quarantined')
    or (mapping.approval_status in ('candidate', 'quarantined')
        and ifNull(actual.unit_code != stocks.stock_unit_code, true)
        and actual.conversion_status != mapping.approval_status)
    or (isNotNull(stocks.stock_unit_id) and actual.unit_code = stocks.stock_unit_code
        and actual.conversion_status != 'identity')
    or (mapping.approval_status = 'approved' and mapping.stock_unit = stocks.stock_unit_code
        and actual.unit_code != stocks.stock_unit_code and actual.conversion_status != 'approved')
    or actual.conversion_status not in ('identity', 'approved', 'candidate', 'quarantined', 'unmapped')
settings join_use_nulls = 1
