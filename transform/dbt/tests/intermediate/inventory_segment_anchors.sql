-- Each segment has one boundary at its minimum source sequence and a recorded anchor.
select dataset_name, product_id, warehouse_id, segment_id
from {{ ref('int_inventory_segments') }}
group by dataset_name, product_id, warehouse_id, segment_id
having countIf(is_ledger_start or is_discontinuity) != 1
    or min(dataset_row_number) != min(segment_start_sequence)
    or uniqExact(segment_start_sequence) != 1
    or uniqExact(segment_end_sequence) != 1
    or max(dataset_row_number) != min(segment_end_sequence)
    or uniqExact(segment_opening_quantity) != 1
    or min(segment_opening_quantity) != argMin(opening_stock_quantity, dataset_row_number)
    or min(segment_started_at) != argMin(movement_at, dataset_row_number)
    or max(segment_ended_at) != argMax(movement_at, dataset_row_number)
    or uniqExact(segment_boundary_reason) != 1
    or min(segment_boundary_reason) != argMin(boundary_reason, dataset_row_number)
    or segment_id != toJSONString(tuple(dataset_name, product_id, warehouse_id, min(dataset_row_number)))
