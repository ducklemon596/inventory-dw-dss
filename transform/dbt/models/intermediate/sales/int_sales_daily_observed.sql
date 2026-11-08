-- INTERMEDIATE: Daily recorded sales in each original unit
-- Grain change: sales invoice line -> product / event date / unit.
-- Approved I-01: keep units separate, with no net-return or location inference.

with recorded_sales as (
    select product_id, sold_date, unit_id, sold_quantity, sold_at
    from {{ ref('int_sales_lines_enriched') }}
)

-- Aggregate only observed combinations; absent dates remain absent.
select
    product_id,
    sold_date,
    unit_id,
    sum(sold_quantity) as recorded_sold_quantity,
    count() as sales_line_count,
    min(sold_at) as first_sold_at,
    max(sold_at) as last_sold_at
from recorded_sales
group by product_id, sold_date, unit_id
