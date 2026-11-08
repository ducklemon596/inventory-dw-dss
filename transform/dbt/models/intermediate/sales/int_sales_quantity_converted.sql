-- UOM: One recorded sales line, enriched with governed stock-unit conversion
-- Original quantities stay untouched. Candidate factors never enter arithmetic.
WITH selected_mapping AS (
    SELECT *
    FROM {{ ref('uom_conversion_mapping') }}
    WHERE mapping_version = {{ uom_mapping_version_literal() }}
),

version_guard AS (
    -- This also protects dbt run; the seed existence test gates dbt build.
    SELECT throwIf(count() = 0, 'Selected UOM mapping version is not published') AS invalid_version
    FROM selected_mapping
),

matched AS (
    SELECT
        sales.sales_invoice_line_id AS sales_invoice_line_id,
        sales.dataset_name AS dataset_name,
        sales.dataset_row_number AS dataset_row_number,
        sales.sales_invoice_id AS sales_invoice_id,
        sales.sales_invoice_number AS sales_invoice_number,
        sales.product_id AS product_id,
        sales.product_code AS product_code,
        sales.unit_id AS unit_id,
        sales.unit_code AS unit_code,
        sales.cashier_id AS cashier_id,
        sales.cashier_code AS cashier_code,
        sales.sold_at AS sold_at,
        sales.sold_date AS sold_date,
        sales.shift_label AS shift_label,
        sales.shift_date AS shift_date,
        sales.shift_period AS shift_period,
        sales.shift_cashier_code AS shift_cashier_code,
        sales.product_name AS product_name,
        sales.manufacturer_name AS manufacturer_name,
        sales.drug_class_name AS drug_class_name,
        sales.category_name AS category_name,
        sales.product_batch_id AS product_batch_id,
        sales.product_batch_label AS product_batch_label,
        sales.product_batch_number AS product_batch_number,
        sales.expiration_date AS expiration_date,
        sales.sold_quantity AS sold_quantity,
        sales.unit_price AS unit_price,
        sales.price_tier_label AS price_tier_label,
        sales.price_tier_number AS price_tier_number,
        sales.discount_percentage AS discount_percentage,
        sales.discount_amount AS discount_amount,
        sales.service_fee_amount AS service_fee_amount,
        sales.packaging_fee_amount AS packaging_fee_amount,
        sales.subtotal_amount AS subtotal_amount,
        sales.invoice_discount_percentage AS invoice_discount_percentage,
        sales.promotional_discount_percentage AS promotional_discount_percentage,
        sales.tax_percentage AS tax_percentage,
        sales.additional_fee_amount AS additional_fee_amount,
        sales.total_amount AS total_amount,
        sales.payment_method AS payment_method,
        sales.document_print_count AS document_print_count,
        sales.membership_status AS membership_status,
        stocks.stock_unit_id AS verified_stock_unit_id,
        stocks.stock_unit_code AS verified_stock_unit_code,
        mapping.tier AS mapping_tier,
        mapping.approval_status AS mapping_approval_status,
        mapping.factor_approved AS approved_conversion_factor,
        mapping.n_supporting_invoices AS mapping_supporting_invoice_count,
        mapping.share_at_mode AS mapping_share_at_mode,
        mapping.price_ratio AS mapping_price_ratio,
        mapping.price_check_within_15pct AS mapping_price_check_within_15pct,
        mapping.evidence_source AS mapping_evidence_source,
        mapping.stock_unit AS mapping_stock_unit_code,
        {{ uom_mapping_version_literal() }} AS mapping_version
    FROM {{ ref('int_sales_lines_enriched') }} AS sales
    LEFT JOIN {{ ref('int_product_stock_units') }} AS stocks
        ON sales.dataset_name = stocks.dataset_name
        AND sales.product_id = stocks.product_id
        AND sales.product_code = stocks.product_code
    LEFT JOIN selected_mapping AS mapping
        -- Mapping product_id is the business DrugCode; the sales product_id is a numeric identity.
        ON sales.product_code = mapping.product_id
        AND sales.unit_code = mapping.sales_unit
    CROSS JOIN version_guard
    WHERE version_guard.invalid_version = 0
        -- An explicit conflicting factor must not be hidden by the identity branch.
        AND throwIf(
            ifNull(
                sales.unit_code = stocks.stock_unit_code
                AND coalesce(mapping.factor_approved, mapping.factor_candidate) != toDecimal64(1, 6),
                FALSE
            ),
            'Explicit UOM factor conflicts with verified identity'
        ) = 0
),

classified AS (
    SELECT
        *,
        multiIf(
            isNotNull(verified_stock_unit_id) AND unit_code = verified_stock_unit_code, 'identity',
            mapping_approval_status = 'approved'
                AND mapping_tier = 'A'
                AND approved_conversion_factor > 0
                AND mapping_stock_unit_code = verified_stock_unit_code, 'approved',
            mapping_approval_status = 'candidate', 'candidate',
            mapping_approval_status = 'quarantined', 'quarantined', 'unmapped'
        ) AS conversion_status
    FROM matched
)
SELECT
    *,
    multiIf(
        conversion_status = 'identity', toNullable(toDecimal64(1, 6)),
        conversion_status = 'approved', approved_conversion_factor,
        CAST(NULL AS Nullable(Decimal(18, 6)))
    ) AS applied_conversion_factor,
    -- Decimal128 * Decimal128 retains all twelve fractional digits, with no float.
    multiIf(
        conversion_status = 'identity', toDecimal128(sold_quantity, 12),
        conversion_status = 'approved', toDecimal128(sold_quantity, 6) * toDecimal128(approved_conversion_factor, 6),
        CAST(NULL AS Nullable(Decimal(38, 12)))
    ) AS stock_unit_qty
FROM classified
