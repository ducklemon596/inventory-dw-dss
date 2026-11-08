-- Keep each product and original unit separate; a Box quantity cannot be added to a Tab quantity.
-- Only observed sales combinations appear, without assigning warehouses or matching stock returns.

WITH recorded_sales AS (
    SELECT
        product_id,
        sold_date,
        unit_id,
        sold_quantity,
        sold_at
    FROM {{ ref('int_sales_lines_enriched') }}
)

SELECT
    product_id,
    sold_date,
    unit_id,
    sum(sold_quantity) AS recorded_sold_quantity,
    count() AS sales_line_count,
    min(sold_at) AS first_sold_at,
    max(sold_at) AS last_sold_at
FROM recorded_sales
GROUP BY product_id, sold_date, unit_id
