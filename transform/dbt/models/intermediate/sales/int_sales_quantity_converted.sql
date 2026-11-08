-- UOM: One recorded sales line, enriched with governed stock-unit conversion
-- Original quantities stay untouched. Candidate factors never enter arithmetic.
with selected_mapping as (
    select * from {{ ref('uom_conversion_mapping') }}
    where mapping_version = {{ uom_mapping_version_literal() }}
), version_guard as (
    -- This also protects dbt run; the seed existence test gates dbt build.
    select throwIf(count() = 0, 'Selected UOM mapping version is not published') as invalid_version
    from selected_mapping
), matched as (
    select
        sales.sales_invoice_line_id as sales_invoice_line_id,
        sales.dataset_name as dataset_name,
        sales.dataset_row_number as dataset_row_number,
        sales.sales_invoice_id as sales_invoice_id,
        sales.sales_invoice_number as sales_invoice_number,
        sales.product_id as product_id,
        sales.product_code as product_code,
        sales.unit_id as unit_id,
        sales.unit_code as unit_code,
        sales.cashier_id as cashier_id,
        sales.cashier_code as cashier_code,
        sales.sold_at as sold_at,
        sales.sold_date as sold_date,
        sales.shift_label as shift_label,
        sales.shift_date as shift_date,
        sales.shift_period as shift_period,
        sales.shift_cashier_code as shift_cashier_code,
        sales.product_name as product_name,
        sales.manufacturer_name as manufacturer_name,
        sales.drug_class_name as drug_class_name,
        sales.category_name as category_name,
        sales.product_batch_id as product_batch_id,
        sales.product_batch_label as product_batch_label,
        sales.product_batch_number as product_batch_number,
        sales.expiration_date as expiration_date,
        sales.sold_quantity as sold_quantity,
        sales.unit_price as unit_price,
        sales.price_tier_label as price_tier_label,
        sales.price_tier_number as price_tier_number,
        sales.discount_percentage as discount_percentage,
        sales.discount_amount as discount_amount,
        sales.service_fee_amount as service_fee_amount,
        sales.packaging_fee_amount as packaging_fee_amount,
        sales.subtotal_amount as subtotal_amount,
        sales.invoice_discount_percentage as invoice_discount_percentage,
        sales.promotional_discount_percentage as promotional_discount_percentage,
        sales.tax_percentage as tax_percentage,
        sales.additional_fee_amount as additional_fee_amount,
        sales.total_amount as total_amount,
        sales.payment_method as payment_method,
        sales.document_print_count as document_print_count,
        sales.membership_status as membership_status,
        stocks.stock_unit_id as verified_stock_unit_id,
        stocks.stock_unit_code as verified_stock_unit_code,
        mapping.tier as mapping_tier,
        mapping.approval_status as mapping_approval_status,
        mapping.factor_approved as approved_conversion_factor,
        mapping.n_supporting_invoices as mapping_supporting_invoice_count,
        mapping.share_at_mode as mapping_share_at_mode,
        mapping.price_ratio as mapping_price_ratio,
        mapping.price_check_within_15pct as mapping_price_check_within_15pct,
        mapping.evidence_source as mapping_evidence_source,
        mapping.stock_unit as mapping_stock_unit_code,
        {{ uom_mapping_version_literal() }} as mapping_version
    from {{ ref('int_sales_lines_enriched') }} as sales
    left join {{ ref('int_product_stock_units') }} as stocks
        on sales.dataset_name = stocks.dataset_name and sales.product_id = stocks.product_id
        and sales.product_code = stocks.product_code
    left join selected_mapping as mapping
        -- Research product_id is DrugCode, not the numeric sales.product_id.
        on sales.product_code = mapping.product_id and sales.unit_code = mapping.sales_unit
    cross join version_guard
    where version_guard.invalid_version = 0
        and throwIf(ifNull(sales.unit_code = stocks.stock_unit_code
                    and coalesce(mapping.factor_approved, mapping.factor_candidate) != toDecimal64(1, 6), false),
                    'Explicit UOM factor conflicts with verified identity') = 0
), classified as (
    select
        *,
        multiIf(
            isNotNull(verified_stock_unit_id) and unit_code = verified_stock_unit_code, 'identity',
            mapping_approval_status = 'approved' and mapping_tier = 'A'
                and approved_conversion_factor > 0 and mapping_stock_unit_code = verified_stock_unit_code, 'approved',
            mapping_approval_status = 'candidate', 'candidate',
            mapping_approval_status = 'quarantined', 'quarantined', 'unmapped'
        ) as conversion_status
    from matched
)
select
    *,
    multiIf(conversion_status = 'identity', toNullable(toDecimal64(1, 6)),
            conversion_status = 'approved', approved_conversion_factor,
            CAST(null AS Nullable(Decimal(18, 6)))) as applied_conversion_factor,
    -- Decimal128 * Decimal128 retains all twelve fractional digits, with no float.
    multiIf(conversion_status = 'identity', toDecimal128(sold_quantity, 12),
            conversion_status = 'approved', toDecimal128(sold_quantity, 6) * toDecimal128(approved_conversion_factor, 6),
            CAST(null AS Nullable(Decimal(38, 12)))) as stock_unit_qty
from classified
