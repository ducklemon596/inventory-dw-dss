-- Every mapped SKU has one compatible stock target across available export scopes.
with observed as (
    select product_code, uniqExact(stock_unit_code) as target_count,
        countIf(isNull(stock_unit_id)) as unverified_scopes, min(stock_unit_code) as observed_stock_unit
    from {{ ref('int_product_stock_units') }} group by product_code
)
select mapping.mapping_version, mapping.product_id, mapping.sales_unit
from {{ ref('uom_conversion_mapping') }} as mapping
left join observed on mapping.product_id = observed.product_code
where observed.product_code is null or observed.target_count != 1 or observed.unverified_scopes > 0
    or mapping.stock_unit != observed.observed_stock_unit
    or (mapping.sales_unit = observed.observed_stock_unit
        and ifNull(coalesce(mapping.factor_approved, mapping.factor_candidate) != toDecimal64(1, 6), false))
settings join_use_nulls = 1
