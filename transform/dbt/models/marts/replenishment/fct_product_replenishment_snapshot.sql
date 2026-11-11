-- FACT: Point-in-time replenishment features and forward outcome labels per product and day
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='(dataset_name, product_id, snapshot_date)'
) }}

-- Features use only days up to and including snapshot_date; labels use only the days after it.
-- Positions are dense per product, so a ROWS frame of N rows is exactly N calendar days.
{% set horizons = [7, 14, 30] %}

WITH positions AS (
    SELECT *
    FROM {{ ref('fct_product_daily_position') }}
),

windowed AS (
    SELECT
        *,
        sum(sold_qty) OVER last_7_days AS sold_qty_7d,
        sum(sold_qty) OVER last_30_days AS sold_qty_30d,
        sum(sold_qty) OVER last_90_days AS sold_qty_90d,
        sum(sales_amount) OVER last_90_days AS sales_amount_90d,
        countIf(sold_qty > 0) OVER last_90_days AS sale_days_90d,
        countIf(has_purchase_receipt = 1) OVER last_90_days AS purchase_receipt_days_90d,
        sum(transfer_to_dispensary_qty) OVER last_30_days AS transfer_to_dispensary_qty_30d,
        countIf(is_dispensary_stockout = 1) OVER last_90_days AS dispensary_stockout_days_90d,
        max(has_stocktake) OVER last_90_days AS has_stocktake_90d,
        stddevPop(toFloat64(sold_qty)) OVER last_90_days AS sold_qty_std_90d,
        max(sold_qty) OVER last_90_days AS sold_qty_max_90d,
        sum(sold_qty) OVER last_365_days AS sold_qty_365d,
        countIf(sold_qty > 0) OVER last_365_days AS sale_days_365d,
        countIf(has_purchase_receipt = 1) OVER last_365_days AS purchase_receipt_days_365d,
        sum(purchase_received_qty) OVER last_365_days AS purchase_received_qty_365d,
        countIf(transfer_to_dispensary_qty > 0) OVER last_90_days AS transfer_days_90d,
        countIf(is_dispensary_stockout = 1) OVER last_365_days AS dispensary_stockout_days_365d,
        avg(toFloat64(dispensary_on_hand_qty)) OVER last_30_days AS dispensary_avg_on_hand_30d,
        min(dispensary_on_hand_qty) OVER last_30_days AS dispensary_min_on_hand_30d,
        max(if(transfer_to_dispensary_qty > 0, position_date, NULL)) OVER history AS last_transfer_date,
        max(if(is_dispensary_stockout = 1, position_date, NULL)) OVER history AS last_stockout_date,
        max(if(sold_qty > 0, position_date, NULL)) OVER history AS last_sale_date,
        max(if(has_purchase_receipt = 1, position_date, NULL)) OVER history AS last_receipt_date,
        row_number() OVER history - 1 AS history_days,
        {%- for horizon in horizons %}
        count() OVER next_{{ horizon }}_days AS observed_days_next_{{ horizon }}d,
        min(dispensary_on_hand_qty) OVER next_{{ horizon }}_days AS min_dispensary_on_hand_next_{{ horizon }}d,
        sum(sold_qty) OVER next_{{ horizon }}_days AS sold_qty_next_{{ horizon }}d,
        max(has_stocktake) OVER next_{{ horizon }}_days AS has_stocktake_next_{{ horizon }}d{% if not loop.last %},{% endif %}
        {%- endfor %}
    FROM positions
    WINDOW
        history AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        last_7_days AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ),
        last_30_days AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ),
        last_90_days AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
        ),
        last_365_days AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date ROWS BETWEEN 364 PRECEDING AND CURRENT ROW
        ),
        {%- for horizon in horizons %}
        next_{{ horizon }}_days AS (
            PARTITION BY dataset_name, product_id ORDER BY position_date
            ROWS BETWEEN 1 FOLLOWING AND {{ horizon }} FOLLOWING
        ){% if not loop.last %},{% endif %}
        {%- endfor %}
),

features AS (
    SELECT
        *,
        greatest(pharmacy_on_hand_qty, 0) AS available_qty,
        toFloat64(sold_qty_90d) / 90 AS avg_daily_sold_qty_90d,
        -- Running 90-day sales value across products of the same day, highest value first (ABC).
        sum(toFloat64(greatest(sales_amount_90d, 0))) OVER value_rank AS cumulative_sales_amount_90d,
        sum(toFloat64(greatest(sales_amount_90d, 0))) OVER same_day AS total_sales_amount_90d
    FROM windowed
    WINDOW
        value_rank AS (
            PARTITION BY dataset_name, position_date ORDER BY sales_amount_90d DESC, product_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        same_day AS (PARTITION BY dataset_name, position_date)
)

SELECT
    dataset_name,
    product_id,
    position_date AS snapshot_date,
    stock_unit_id,
    is_consignment,

    -- Position at the end of snapshot_date, in the product's stock unit.
    dispensary_on_hand_qty,
    storeroom_on_hand_qty,
    pharmacy_on_hand_qty,
    available_qty,

    -- Demand history. Quantities are ledger issues, so they share the stock unit with the balances.
    sold_qty_7d,
    sold_qty_30d,
    sold_qty_90d,
    toUInt8(sale_days_90d) AS sale_days_90d,
    avg_daily_sold_qty_90d,
    sales_amount_90d,
    -- Sales value per stock unit; serves as a price proxy for value-based budgets.
    if(sold_qty_90d > 0, toFloat64(sales_amount_90d) / toFloat64(sold_qty_90d), NULL) AS unit_sales_value_90d,

    -- Coverage. NULL when there were no sales, because coverage is then unbounded.
    if(avg_daily_sold_qty_90d > 0, toFloat64(available_qty) / avg_daily_sold_qty_90d, NULL) AS pharmacy_days_of_supply,
    if(
        avg_daily_sold_qty_90d > 0,
        toFloat64(greatest(dispensary_on_hand_qty, 0)) / avg_daily_sold_qty_90d,
        NULL
    ) AS dispensary_days_of_supply,

    -- Replenishment and service history.
    toNullable(toUInt32(dateDiff('day', last_sale_date, position_date))) AS days_since_last_sale,
    toNullable(toUInt32(dateDiff('day', last_receipt_date, position_date))) AS days_since_last_receipt,
    toUInt8(purchase_receipt_days_90d) AS purchase_receipt_days_90d,
    transfer_to_dispensary_qty_30d,
    toUInt8(dispensary_stockout_days_90d) AS dispensary_stockout_days_90d,
    toUInt32(history_days) AS history_days,
    has_stocktake_90d,

    -- Demand shape. Peak-day cover was the strongest stockout predictor in backtests.
    sold_qty_std_90d,
    sold_qty_max_90d,
    if(avg_daily_sold_qty_90d > 0, sold_qty_std_90d / avg_daily_sold_qty_90d, NULL) AS demand_cv_90d,
    if(avg_daily_sold_qty_90d > 0, toFloat64(sold_qty_7d) / (avg_daily_sold_qty_90d * 7), NULL) AS demand_trend_7_90,
    if(
        sold_qty_max_90d > 0,
        toFloat64(greatest(dispensary_on_hand_qty, 0)) / toFloat64(sold_qty_max_90d),
        NULL
    ) AS dispensary_peak_cover_days,
    sold_qty_365d,
    toUInt16(sale_days_365d) AS sale_days_365d,

    -- Replenishment rhythm over the last year and the dispensary refill pattern.
    toUInt16(purchase_receipt_days_365d) AS purchase_receipt_days_365d,
    if(
        purchase_receipt_days_365d > 0,
        toFloat64(purchase_received_qty_365d) / purchase_receipt_days_365d,
        NULL
    ) AS avg_purchase_receipt_qty_365d,
    toUInt8(transfer_days_90d) AS transfer_days_90d,
    toNullable(toUInt32(dateDiff('day', last_transfer_date, position_date))) AS days_since_last_transfer,
    dispensary_avg_on_hand_30d,
    dispensary_min_on_hand_30d,
    toNullable(toUInt32(dateDiff('day', last_stockout_date, position_date))) AS days_since_last_stockout,
    toUInt16(dispensary_stockout_days_365d) AS dispensary_stockout_days_365d,

    -- Eligibility. Consignment stock is supplied by its owner and is not purchased by the pharmacy.
    toUInt8(sold_qty_90d > 0) AS is_active_90d,
    toUInt8(history_days >= 89) AS has_full_history,
    toUInt8(sold_qty_90d > 0 AND is_consignment = 0 AND has_dispensary_ledger = 1) AS is_orderable,

    -- ABC by 90-day sales value: A = first 80% of the day's value, B = next 15%, C = the rest.
    -- The share before the product decides, so the top seller is always A. NULL without sales value.
    multiIf(
        sales_amount_90d <= 0, NULL,
        (cumulative_sales_amount_90d - toFloat64(sales_amount_90d)) / total_sales_amount_90d < 0.80, 'A',
        (cumulative_sales_amount_90d - toFloat64(sales_amount_90d)) / total_sales_amount_90d < 0.95, 'B',
        'C'
    ) AS abc_class,

    -- Labels are NULL until the whole horizon is observed in the export.
    {%- for horizon in horizons %}
    if(
        observed_days_next_{{ horizon }}d = {{ horizon }},
        toUInt8(min_dispensary_on_hand_next_{{ horizon }}d <= 0),
        NULL
    ) AS label_dispensary_stockout_{{ horizon }}d,
    if(observed_days_next_{{ horizon }}d = {{ horizon }}, sold_qty_next_{{ horizon }}d, NULL) AS label_sold_qty_{{ horizon }}d,
    -- Purchase-relevant shortfall: sales in the window reach all stock held at T, so without a new
    -- receipt the pharmacy would run out. Unlike the dispensary label it ignores how promptly the
    -- shelf was refilled, which reflects past manager actions rather than risk.
    if(
        observed_days_next_{{ horizon }}d = {{ horizon }},
        toUInt8(sold_qty_next_{{ horizon }}d >= available_qty),
        NULL
    ) AS label_pharmacy_shortfall_{{ horizon }}d,
    if(
        observed_days_next_{{ horizon }}d = {{ horizon }},
        has_stocktake_next_{{ horizon }}d,
        NULL
    ) AS label_window_has_stocktake_{{ horizon }}d{% if not loop.last %},{% endif %}
    {%- endfor %}
FROM features
