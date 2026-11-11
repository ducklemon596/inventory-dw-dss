-- Product positions must equal the warehouse positions they aggregate and keep every sales line value.
{% set dispensary_id = var('replenishment_dispensary_warehouse_id') %}
with expected as (
    select dataset_name, product_id, position_date,
        sumIf(on_hand_qty, warehouse_id = {{ dispensary_id }}) as dispensary,
        sumIf(on_hand_qty, warehouse_id != {{ dispensary_id }}) as storeroom,
        sum(sold_qty) as sold, sum(purchase_received_qty) as purchased,
        sum(adjustment_qty) as adjusted, sum(movement_count) as movements
    from {{ ref('int_inventory_daily_position') }}
    group by dataset_name, product_id, position_date
), sales as (
    select dataset_name, product_id, sold_date, sum(subtotal_amount) as amount
    from {{ ref('fct_sales_line') }}
    group by dataset_name, product_id, sold_date
)
select coalesce(expected.product_id, actual.product_id) as product_id
from expected
full outer join {{ ref('fct_product_daily_position') }} as actual
    on expected.dataset_name = actual.dataset_name and expected.product_id = actual.product_id
    and expected.position_date = actual.position_date
where expected.product_id is null or actual.product_id is null
    or actual.dispensary_on_hand_qty != expected.dispensary
    or actual.storeroom_on_hand_qty != expected.storeroom
    or actual.pharmacy_on_hand_qty != expected.dispensary + expected.storeroom
    or actual.sold_qty != expected.sold
    or actual.purchase_received_qty != expected.purchased
    or actual.adjustment_qty != expected.adjusted
    or actual.movement_count != expected.movements
    or actual.is_dispensary_stockout != (expected.dispensary <= 0)
union all
-- Stock-tracked products must keep every sales day. Products without any ledger (services such as
-- blood tests) are outside replenishment scope by design.
select sales.product_id
from sales
inner join (select distinct dataset_name, product_id from {{ ref('int_inventory_daily_flows') }}) as tracked
    on sales.dataset_name = tracked.dataset_name and sales.product_id = tracked.product_id
left anti join {{ ref('fct_product_daily_position') }} as actual
    on sales.dataset_name = actual.dataset_name and sales.product_id = actual.product_id
    and sales.sold_date = actual.position_date
settings join_use_nulls = 1
