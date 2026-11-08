# Inventory Intermediate

These models reconstruct **recorded observations** using the verified export sequence. Opening is the recorded balance before a row; received/issued are its flows; closing is the recorded balance after it. `recorded_delta_qty = received_quantity - issued_quantity`. Movement type never assigns a sign.

Run the inventory chain and current dimensions:

```bash
uv run --locked dbt build --select +fct_inventory_daily_observed diag_inventory_ledger_discontinuities dim_product dim_warehouse dim_unit dim_date --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

Use `dbt test --select MODEL_NAME` with the same options for existing relations. Full tests and read-only export reconciliation are explained in [test guidance](../../../tests/README.md). Contracts: [_movements.yml](_movements.yml), [_inventory_history.yml](_inventory_history.yml). [Source evidence](../../../../../docs/source-system.md) establishes ordering for this vintage.

### Model: `int_inventory_movements_enriched`

**Purpose:** Add business labels, recorded flow and quality flags to each movement.

**Grain:** One source inventory movement, inventory_movement_id. Materialization: **view**.

**Inputs:** [stg_inventory_movements](../../staging/inventory/stg_inventory_movements.sql), [stg_inventory_documents](../../staging/inventory/stg_inventory_documents.sql), [stg_products](../../staging/reference/stg_products.sql), [stg_warehouses](../../staging/reference/stg_warehouses.sql), [stg_units](../../staging/reference/stg_units.sql).

**Main logic:**

1. Start from every typed movement.
2. LEFT JOIN document, product, warehouse and the four unit roles without filtering.
3. Derive movement_date, inbound-minus-outbound recorded delta and negative/UNKNOWN flags.

**Important columns:** Source dataset/row, movement/document/product/warehouse IDs, all four quantities/unit roles, `recorded_delta_qty`, `has_negative_opening_stock`, `has_negative_closing_stock`, `is_unknown_movement`.

**Output:** `int_inventory_ledger_ordered`

**Business rules:** Preserve UNKNOWN, zero-flow, negative and both RETURN directions. No return-sales linkage, balance repair or movement-type sign inference.

**How to modify it safely:** Confirm lookup uniqueness, full source preservation and exact opening + received - issued = closing. Do not introduce JOIN fan-out.

**Tests:** `inventory_recorded_balance`, unique grain, source preservation, declared relationships and native RETURN/UNKNOWN/negative fixture. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_movements.yml](_movements.yml).

### Model: `int_inventory_ledger_ordered`

**Purpose:** Attach each movement to its preceding recorded observation and check continuity.

**Grain:** One source movement within a (dataset_name,product_id,warehouse_id) ledger. Materialization: **table**.

**Inputs:** [int_inventory_movements_enriched](int_inventory_movements_enriched.sql).

**Main logic:**

1. Partition enriched rows by dataset/product/warehouse and order by dataset_row_number.
2. Use lagInFrame for prior ID, source sequence, time, closing quantity/unit and description.
3. Mark ledger start and compare current opening with previous closing; record the difference and boundary reason.

**Important columns:** `previous_movement_id`, `previous_source_sequence`, `previous_closing_quantity`, `continuity_delta_qty`, `is_ledger_start`, `is_discontinuity`, `is_continuous`, `boundary_reason`.

**Output:** `int_inventory_segments`

**Business rules:** The ordering key is export sequence, not generated numeric ID or event timestamp. Gap difference is diagnostic, not movement quantity.

**How to modify it safely:** Retain full-ledger windows and exact unit/Decimal semantics. Validate source sequence before changing order; test predecessor association and source preservation.

**Tests:** `inventory_ledger_predecessors`, `inventory_ledger_units`, unique source/grain, preservation and native ledger fixture. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_inventory_history.yml](_inventory_history.yml).

### Model: `int_inventory_segments`

**Purpose:** Anchor continuous portions of a ledger separately and reconstruct their recorded closings.

**Grain:** One movement assigned to one segment; segment ID encodes dataset/product/warehouse/start sequence. Materialization: **table**.

**Inputs:** [int_inventory_ledger_ordered](int_inventory_ledger_ordered.sql).

**Main logic:**

1. Use a running maximum of start/discontinuity sequences to assign segment_start_sequence.
2. Build an unambiguous JSON tuple segment ID and determine segment end, opening/time/boundary metadata.
3. Accumulate exact Decimal(38,6) recorded deltas inside each segment.
4. Add the segment opening anchor to the running delta to obtain reconstructed_closing_quantity.

**Important columns:** `segment_id`, start/end sequence, opening quantity, started/ended time, boundary reason, `segment_cumulative_delta_qty`, `reconstructed_closing_quantity`.

**Output:** `diag_inventory_ledger_discontinuities`, `fct_inventory_movement`

**Business rules:** A gap starts a fresh anchor; it does not add an adjustment movement. Reconstruction checks internal agreement, not certified physical stock.

**How to modify it safely:** Full rebuild is intentional: early changes split/merge segments and appends can extend prior rows' end metadata. Keep anchors/order/arithmetic and compare every source movement.

**Tests:** `inventory_segment_anchors`, `inventory_segment_reconstruction`, unique grain, preservation and native segment fixture; read-only history validator. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_inventory_history.yml](_inventory_history.yml).

#### Continuity and segment example

| Source sequence | Opening | Received | Issued | Closing | Segment start | Reason |
|---|---:|---:|---:|---:|---:|---|
| 10 | 10 | 5 | 3 | 12 | 10 | Ledger start |
| 11 | 12 | 0 | 2 | 10 | 10 | Continuous |
| 12 | 20 | 0 | 1 | 19 | 12 | Opening differs from previous closing |

The first segment reconstructs 12 then 10 from anchor 10. The second starts from recorded opening 20 and reconstructs 19. The difference `20 - 10 = 10` remains a gap diagnostic; it is not an extra receipt, inferred stocktake adjustment or demand. Source sequences need not be consecutive within a product ledger because they originate in the full export.

### Model: `diag_inventory_ledger_discontinuities`

**Purpose:** Expose observed ledger gaps with adjacent context for investigation.

**Grain:** One discontinuous source movement, inventory_movement_id. Materialization: **view**.

**Inputs:** [int_inventory_segments](int_inventory_segments.sql).

**Main logic:**

1. Read complete segment rows and calculate the preceding segment ID within the source-ordered ledger.
2. Keep rows marked is_discontinuity.
3. Label whether one, both or neither adjacent descriptions mention the stocktake keyword; retain both observations and gap quantity.

**Important columns:** Movement/prior IDs and source sequences/times, previous closing/current opening, `continuity_delta_qty`, segment IDs, `diagnostic_class`, `diagnostic_evidence`.

**Output:** DSS queries and analytical joins; no downstream SQL model is configured.

**Business rules:** Description keywords do not establish stocktake batches, cancellation or adjustment rules. Diagnostics are not a movement measure.

**How to modify it safely:** Preserve the full window before filtering gaps. Avoid making a keyword match authorize inventory correction; retain all observed gaps.

**Tests:** `inventory_discontinuity_diagnostics`, unique grain and required identifier checks; history validator checks complete gap coverage. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_inventory_history.yml](_inventory_history.yml).
