-- Every SKU/unit group's quantities stay in that same original unit.
with source as (
    select dataset_name, product_id, unit_id, count() as lines, sum(abs(sold_quantity)) as quantity
    from {{ ref('int_sales_lines_enriched') }} group by dataset_name, product_id, unit_id
)
select coalesce(source.product_id, actual.product_id) as product_id
from source full outer join {{ ref('int_sales_uom_coverage') }} as actual
    on source.dataset_name = actual.dataset_name and source.product_id = actual.product_id
    and source.unit_id = actual.unit_id
where source.product_id is null or actual.product_id is null
    or actual.mapping_version != {{ uom_mapping_version_literal() }}
    or actual.sales_line_count != source.lines or actual.absolute_sales_quantity != source.quantity
    or actual.covered_absolute_sales_quantity + actual.unresolved_absolute_sales_quantity != source.quantity
    or actual.identity_line_count + actual.approved_line_count + actual.candidate_line_count
        + actual.quarantined_line_count + actual.unmapped_line_count != source.lines
settings join_use_nulls = 1
