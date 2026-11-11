-- Recompute window features and labels by date arithmetic for month-start snapshots.
-- Independent of the model's ROWS frames, so it also proves that positions are dense.
with snapshots as (
    select *
    from {{ ref('fct_product_replenishment_snapshot') }}
    where toDayOfMonth(snapshot_date) = 1
), positions as (
    select dataset_name, product_id, position_date, sold_qty, dispensary_on_hand_qty, is_dispensary_stockout
    from {{ ref('fct_product_daily_position') }}
), export_end as (
    select max(position_date) as last_date from positions
), expected as (
    select snapshots.dataset_name as dataset_name, snapshots.product_id as product_id,
        snapshots.snapshot_date as snapshot_date,
        sumIf(positions.sold_qty, positions.position_date > snapshots.snapshot_date - 7
            and positions.position_date <= snapshots.snapshot_date) as sold_7d,
        sumIf(positions.sold_qty, positions.position_date > snapshots.snapshot_date - 90
            and positions.position_date <= snapshots.snapshot_date) as sold_90d,
        countIf(positions.is_dispensary_stockout = 1 and positions.position_date > snapshots.snapshot_date - 90
            and positions.position_date <= snapshots.snapshot_date) as stockout_days_90d,
        sumIf(positions.sold_qty, positions.position_date > snapshots.snapshot_date
            and positions.position_date <= snapshots.snapshot_date + 30) as sold_next_30d,
        maxIf(toUInt8(positions.dispensary_on_hand_qty <= 0), positions.position_date > snapshots.snapshot_date
            and positions.position_date <= snapshots.snapshot_date + 30) as stockout_next_30d
    from snapshots
    inner join positions on snapshots.dataset_name = positions.dataset_name
        and snapshots.product_id = positions.product_id
        and positions.position_date > snapshots.snapshot_date - 90
        and positions.position_date <= snapshots.snapshot_date + 30
    group by snapshots.dataset_name, snapshots.product_id, snapshots.snapshot_date
)
select actual.product_id, actual.snapshot_date
from snapshots as actual
inner join expected on actual.dataset_name = expected.dataset_name and actual.product_id = expected.product_id
    and actual.snapshot_date = expected.snapshot_date
cross join export_end
where actual.sold_qty_7d != expected.sold_7d
    or actual.sold_qty_90d != expected.sold_90d
    or actual.dispensary_stockout_days_90d != expected.stockout_days_90d
    or (actual.snapshot_date + 30 <= export_end.last_date and (
        actual.label_sold_qty_30d is null or actual.label_sold_qty_30d != expected.sold_next_30d
        or actual.label_dispensary_stockout_30d != expected.stockout_next_30d))
    or (actual.snapshot_date + 30 > export_end.last_date and actual.label_dispensary_stockout_30d is not null)
