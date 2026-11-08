-- Source IDs remain positive. Zero is reserved exclusively for unverified stock-unit evidence.
SELECT 'reserved_source_key' AS violation
FROM {{ ref('stg_units') }}
WHERE unit_id = 0

UNION ALL

SELECT 'invalid_special_member' AS violation
FROM {{ ref('dim_unit') }}
WHERE unit_id = 0
HAVING count() != 1
    OR countIf(unit_code = 'NOT_VERIFIED_STOCK_UNIT') != 1

UNION ALL

-- Original sales and recorded inventory units must continue to identify physical source units.
SELECT 'special_member_used_as_physical_unit' AS violation
WHERE EXISTS (SELECT 1 FROM {{ ref('fct_sales_line') }} WHERE unit_id = 0)
    OR EXISTS (
        SELECT 1 FROM {{ ref('fct_inventory_movement') }}
        WHERE opening_stock_unit_id = 0 OR received_unit_id = 0
            OR issued_unit_id = 0 OR closing_stock_unit_id = 0
    )
    OR EXISTS (SELECT 1 FROM {{ ref('fct_inventory_daily_observed') }} WHERE stock_unit_id = 0)
