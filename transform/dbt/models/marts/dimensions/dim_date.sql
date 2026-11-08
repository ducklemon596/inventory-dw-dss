-- Calendar coverage does not create sales activity or inventory observations.
{{ config(materialized='table', engine='MergeTree()', order_by='calendar_date') }}

with event_bounds as (
    select
        minOrNull(toDate32(sold_at)) as first_event_date,
        maxOrNull(toDate32(sold_at)) as last_event_date
    from {{ ref('stg_sales_invoice_lines') }}
    union all
    select
        minOrNull(toDate32(movement_at)) as first_event_date,
        maxOrNull(toDate32(movement_at)) as last_event_date
    from {{ ref('stg_inventory_movements') }}
), calendar_bounds as (
    select
        toDate32(concat(toString(toYear(min(first_event_date))), '-01-01')) as first_date,
        toDate32(concat(toString(toYear(max(last_event_date))), '-12-31')) as last_date
    from event_bounds
), calendar as (
    select
        toDate32(addDays(assumeNotNull(first_date), day_offset)) as calendar_date
    from calendar_bounds
    -- No event bounds means an empty calendar, never a synthetic epoch date.
    array join range(toUInt32(ifNull(dateDiff('day', first_date, last_date) + 1, 0))) as day_offset
)
select
    calendar_date,
    toUInt16(toYear(calendar_date)) as calendar_year,
    toUInt8(toQuarter(calendar_date)) as calendar_quarter,
    toUInt8(toMonth(calendar_date)) as calendar_month,
    toUInt8(toDayOfMonth(calendar_date)) as day_of_month,
    toUInt8(toDayOfWeek(calendar_date)) as iso_day_of_week,
    toUInt8(toISOWeek(calendar_date)) as iso_week,
    toUInt16(toISOYear(calendar_date)) as iso_year,
    toDate32(addDays(calendar_date, 1 - toInt32(toDayOfMonth(calendar_date)))) as month_start_date,
    toUInt8(toDayOfWeek(calendar_date) > 5) as is_weekend
from calendar
