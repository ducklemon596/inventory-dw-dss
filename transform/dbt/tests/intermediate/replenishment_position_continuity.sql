-- Dense positions must be contiguous, match every observed closing and roll forward by daily flows.
with positions as (
    select *,
        lagInFrame(position_date) over ledger as previous_date,
        lagInFrame(on_hand_qty) over ledger as previous_on_hand,
        row_number() over ledger as day_number
    from {{ ref('int_inventory_daily_position') }}
    window ledger as (
        partition by dataset_name, product_id, warehouse_id order by position_date
        rows between unbounded preceding and unbounded following
    )
), flows as (
    select * from {{ ref('int_inventory_daily_flows') }}
), net as (
    select positions.*,
        sold_qty * -1 + customer_return_qty + purchase_received_qty + transfer_in_qty - transfer_out_qty
            + adjustment_qty + balance_gap_qty as net_change
    from positions
)
select net.product_id, net.warehouse_id, net.position_date
from net
left join flows on net.dataset_name = flows.dataset_name and net.product_id = flows.product_id
    and net.warehouse_id = flows.warehouse_id and net.position_date = flows.position_date
where (net.day_number > 1 and dateDiff('day', net.previous_date, net.position_date) != 1)
    or (net.has_movement = 1 and net.on_hand_qty != flows.closing_stock_quantity)
    or (net.has_movement = 0 and (net.on_hand_qty != net.previous_on_hand or net.net_change != 0))
    -- Ledger start rolls from the recorded opening; later days roll from the previous closing.
    or (net.day_number = 1 and net.on_hand_qty != flows.opening_stock_quantity + net.net_change)
    or (net.day_number > 1 and net.on_hand_qty != net.previous_on_hand + net.net_change)
settings join_use_nulls = 1
