-- Count-based coverage is comparable across units; quantity coverage is SKU/unit-specific.
with selected as (
    select *, isNotNull(verified_stock_unit_id) and unit_code != verified_stock_unit_code as needs_conversion
    from {{ ref('int_sales_quantity_converted') }}
    where mapping_version = {{ uom_mapping_version_literal() }}
), totals as (
    select mapping_version,
        count() as sales_lines,
        countIf(needs_conversion) as conversion_needed_lines,
        countIf(conversion_status = 'identity') as identity_lines,
        countIf(conversion_status = 'approved') as approved_lines,
        countIf(conversion_status = 'candidate') as candidate_lines,
        countIf(conversion_status = 'quarantined') as quarantined_lines,
        countIf(conversion_status = 'unmapped') as unmapped_lines,
        countIf(isNull(verified_stock_unit_id)) as lines_without_stock_unit_evidence,
        uniqExactIf(tuple(dataset_name, product_id, unit_id), needs_conversion) as conversion_needed_pairs,
        uniqExactIf(tuple(dataset_name, product_id, unit_id), needs_conversion and conversion_status = 'approved') as approved_pairs
    from selected group by mapping_version
), sku_pairs as (
    select dataset_name, product_id,
        count() as unit_pairs, countIf(approved_line_count > 0) as approved_unit_pairs
    from {{ ref('int_sales_uom_coverage') }}
    where mapping_version = {{ uom_mapping_version_literal() }}
        and isNotNull(verified_stock_unit_code) and unit_code != verified_stock_unit_code
    group by dataset_name, product_id
), sku_counts as (
    select count() as conversion_needed_skus,
        countIf(approved_unit_pairs = unit_pairs) as fully_covered_skus,
        countIf(approved_unit_pairs > 0 and approved_unit_pairs < unit_pairs) as partially_covered_skus,
        countIf(approved_unit_pairs = 0) as unresolved_skus
    from sku_pairs
)
select
    totals.*,
    sku_counts.*,
    if(conversion_needed_lines = 0, CAST(null AS Nullable(Decimal(76, 6))),
       divideDecimal(toDecimal256(approved_lines, 0) * toDecimal256(100, 0),
                     toDecimal256(if(conversion_needed_lines = 0, 1, conversion_needed_lines), 0), 6)
    ) as conversion_needed_row_coverage_percent
from totals cross join sku_counts
