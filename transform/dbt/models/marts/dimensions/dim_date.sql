-- Calendar coverage does not create sales activity or inventory observations.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='calendar_date'
) }}

WITH event_bounds AS (
    SELECT
        minOrNull(toDate32(sold_at)) AS first_event_date,
        maxOrNull(toDate32(sold_at)) AS last_event_date
    FROM {{ ref('stg_sales_invoice_lines') }}
    UNION ALL
    SELECT
        minOrNull(toDate32(movement_at)) AS first_event_date,
        maxOrNull(toDate32(movement_at)) AS last_event_date
    FROM {{ ref('stg_inventory_movements') }}
),

calendar_bounds AS (
    SELECT
        toDate32(concat(toString(toYear(min(first_event_date))), '-01-01')) AS first_date,
        toDate32(concat(toString(toYear(max(last_event_date))), '-12-31')) AS last_date
    FROM event_bounds
),

calendar AS (
    SELECT
        toDate32(addDays(assumeNotNull(first_date), day_offset)) AS calendar_date
    FROM calendar_bounds
    -- No event bounds means an empty calendar, never a synthetic epoch date.
    ARRAY JOIN range(toUInt32(ifNull(dateDiff('day', first_date, last_date) + 1, 0))) AS day_offset
)

SELECT
    calendar_date,
    toUInt16(toYear(calendar_date)) AS calendar_year,
    toUInt8(toQuarter(calendar_date)) AS calendar_quarter,
    toUInt8(toMonth(calendar_date)) AS calendar_month,
    toUInt8(toDayOfMonth(calendar_date)) AS day_of_month,
    toUInt8(toDayOfWeek(calendar_date)) AS iso_day_of_week,
    toUInt8(toISOWeek(calendar_date)) AS iso_week,
    toUInt16(toISOYear(calendar_date)) AS iso_year,
    toDate32(addDays(calendar_date, 1 - toInt32(toDayOfMonth(calendar_date)))) AS month_start_date,
    toUInt8(toDayOfWeek(calendar_date) > 5) AS is_weekend
FROM calendar
