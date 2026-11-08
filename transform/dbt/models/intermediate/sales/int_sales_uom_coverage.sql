-- COVERAGE: Export / product / original sales unit / mapping version
-- Absolute quantities remain in one product's original unit; never pool Box/Tab/etc.
SELECT
    dataset_name,
    product_id,
    product_code,
    unit_id,
    unit_code,
    mapping_version,
    any(verified_stock_unit_code) AS verified_stock_unit_code,
    count() AS sales_line_count,
    countIf(conversion_status = 'identity') AS identity_line_count,
    countIf(conversion_status = 'approved') AS approved_line_count,
    countIf(conversion_status = 'candidate') AS candidate_line_count,
    countIf(conversion_status = 'quarantined') AS quarantined_line_count,
    countIf(conversion_status = 'unmapped') AS unmapped_line_count,
    sum(abs(sold_quantity)) AS absolute_sales_quantity,
    sumIf(abs(sold_quantity), conversion_status IN ('identity', 'approved')) AS covered_absolute_sales_quantity,
    sumIf(abs(sold_quantity), conversion_status NOT IN ('identity', 'approved')) AS unresolved_absolute_sales_quantity
FROM {{ ref('int_sales_quantity_converted') }}
GROUP BY
    dataset_name,
    product_id,
    product_code,
    unit_id,
    unit_code,
    mapping_version
