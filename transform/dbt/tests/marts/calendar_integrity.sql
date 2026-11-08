with source_bounds as (
    select minOrNull(toDate32(sold_at)) as first_date, maxOrNull(toDate32(sold_at)) as last_date
    from {{ ref('stg_sales_invoice_lines') }}
    union all
    select minOrNull(toDate32(movement_at)), maxOrNull(toDate32(movement_at))
    from {{ ref('stg_inventory_movements') }}
), bounds as (
    select min(first_date) as first_event_date, max(last_date) as last_event_date
    from source_bounds
), observed as (
    select count() as dates, minOrNull(calendar_date) as first_date, maxOrNull(calendar_date) as last_date
    from {{ ref('dim_date') }}
)
select 'calendar_coverage' as issue
from bounds cross join observed
where if(first_event_date is null, dates != 0,
    dates = 0
    or toYear(first_date) != toYear(first_event_date) or toMonth(first_date) != 1 or toDayOfMonth(first_date) != 1
    or toYear(last_date) != toYear(last_event_date) or toMonth(last_date) != 12 or toDayOfMonth(last_date) != 31
    or dates != dateDiff('day', first_date, last_date) + 1)
union all
select 'calendar_attributes' as issue
from {{ ref('dim_date') }}
where calendar_year != toYear(calendar_date)
    or calendar_quarter != toQuarter(calendar_date)
    or calendar_month != toMonth(calendar_date)
    or day_of_month != toDayOfMonth(calendar_date)
    or iso_day_of_week != toDayOfWeek(calendar_date)
    or iso_week != toWeek(calendar_date, 3)
    or iso_year != toYear(addDays(calendar_date, 4 - toInt32(iso_day_of_week)))
    or toYear(month_start_date) != calendar_year or toMonth(month_start_date) != calendar_month
    or toDayOfMonth(month_start_date) != 1
    or is_weekend != toUInt8(iso_day_of_week in (6, 7))
