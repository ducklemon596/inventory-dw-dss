-- =============================================================================
-- DATA QUALITY: Recorded inventory effect, units and row-level balance
-- =============================================================================
-- Strict decimal equality; no tolerance, float conversion or repair.
select
    inventory_movement_id,
    opening_stock_quantity,
    received_quantity,
    issued_quantity,
    closing_stock_quantity,
    recorded_delta_qty
from {{ ref('int_inventory_movements_enriched') }}
where opening_stock_unit_id != received_unit_id
    or opening_stock_unit_id != issued_unit_id
    or opening_stock_unit_id != closing_stock_unit_id
    or recorded_delta_qty != received_quantity - issued_quantity
    or opening_stock_quantity + received_quantity - issued_quantity != closing_stock_quantity
    or has_negative_opening_stock != (opening_stock_quantity < 0)
    or has_negative_closing_stock != (closing_stock_quantity < 0)
    or is_unknown_movement != ifNull(transaction_type = 'UNKNOWN', false)
    or movement_date != toDate32(movement_at)
