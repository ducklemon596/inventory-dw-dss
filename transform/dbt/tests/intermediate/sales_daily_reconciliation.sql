-- =============================================================================
-- DATA QUALITY: Exact daily sales reconciliation in the original unit
-- =============================================================================
-- Independently aggregate staging so enrichment errors cannot self-reconcile.
with expected as (
    select
        product_id,
        toDate32(sold_at) as sold_date,
        unit_id,
        sum(sold_quantity) as recorded_sold_quantity,
        count() as sales_line_count,
        min(sold_at) as first_sold_at,
        max(sold_at) as last_sold_at
    from {{ ref('stg_sales_invoice_lines') }}
    group by product_id, sold_date, unit_id
),
actual as (
    select * from {{ ref('int_sales_daily_observed') }}
)

-- Compare both directions: no extra/absent groups, quantities or observations.
select
    coalesce(expected.product_id, actual.product_id) as product_id,
    coalesce(expected.sold_date, actual.sold_date) as sold_date,
    coalesce(expected.unit_id, actual.unit_id) as unit_id,
    expected.recorded_sold_quantity as expected_quantity,
    actual.recorded_sold_quantity as actual_quantity,
    expected.sales_line_count as expected_line_count,
    actual.sales_line_count as actual_line_count
from expected
full outer join actual
    on expected.product_id = actual.product_id
    and expected.sold_date = actual.sold_date
    and expected.unit_id = actual.unit_id
where expected.product_id is null
    or actual.product_id is null
    or expected.recorded_sold_quantity != actual.recorded_sold_quantity
    or expected.sales_line_count != actual.sales_line_count
    or expected.first_sold_at != actual.first_sold_at
    or expected.last_sold_at != actual.last_sold_at
settings join_use_nulls = 1
