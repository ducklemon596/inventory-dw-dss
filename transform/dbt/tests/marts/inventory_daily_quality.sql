-- Diagnose latest-timestamp conflicts independently of the daily model's window.
with latest as (
    select dataset_name, product_id, warehouse_id, movement_date,
        max(movement_at) as latest_at, countIf(is_discontinuity) as gaps,
        uniqExact(segment_id) as segments, argMax(segment_id, dataset_row_number) as last_segment
    from {{ ref('int_inventory_segments') }}
    group by dataset_name, product_id, warehouse_id, movement_date
), conflicts as (
    select source.dataset_name as dataset_name, source.product_id as product_id,
        source.warehouse_id as warehouse_id, source.movement_date as movement_date,
        uniqExact(source.closing_stock_quantity) > 1 as ambiguous
    from {{ ref('int_inventory_segments') }} as source
    inner join latest on source.dataset_name = latest.dataset_name and source.product_id = latest.product_id
        and source.warehouse_id = latest.warehouse_id and source.movement_date = latest.movement_date
        and source.movement_at = latest.latest_at
    group by source.dataset_name, source.product_id, source.warehouse_id, source.movement_date
)
select actual.product_id
from {{ ref('fct_inventory_daily_observed') }} as actual
inner join latest on actual.dataset_name = latest.dataset_name and actual.product_id = latest.product_id
    and actual.warehouse_id = latest.warehouse_id and actual.observation_date = latest.movement_date
inner join conflicts on actual.dataset_name = conflicts.dataset_name and actual.product_id = conflicts.product_id
    and actual.warehouse_id = conflicts.warehouse_id and actual.observation_date = conflicts.movement_date
where actual.discontinuity_count != latest.gaps
    or actual.segment_count != latest.segments
    or actual.last_segment_id != latest.last_segment
    or actual.has_discontinuity != (latest.gaps > 0)
    or actual.has_negative_closing_stock != (actual.observed_closing_quantity < 0)
    or actual.has_ambiguous_latest_timestamp != conflicts.ambiguous
    or actual.stock_unit_count != 1
