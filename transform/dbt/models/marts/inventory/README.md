# Inventory Facts

These tables expose recorded flows and **observed** balances. They do not certify physical/available inventory or create unobserved dates. Full-rebuild tables depend on the validated ledger/segment chain. [_inventory.yml](_inventory.yml) gives every field and test.

```bash
uv run --locked dbt build --select +fct_inventory_daily_observed dim_product dim_warehouse dim_unit dim_date --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

Use the full build to include diagnostics and other business branches. See [data meanings](../../../../../docs/data-semantics.md) and [historical validation](../../../../../docs/data-semantics.md).

### Model: `fct_inventory_movement`

**Purpose:** Publish source stock movements with segment membership and quality diagnostics.

**Grain:** One inventory_movement_id; alternate unique dataset/source row. Materialization: **table**.

**Inputs:** [int_inventory_segments](../../intermediate/inventory/int_inventory_segments.sql).

**Main logic:**

1. Read all reconstructed segment rows.
2. Explicitly retain the 36 source/lineage/quantity/segment/diagnostic fields required by the fact.
3. Fully rebuild, sorted by dataset/product/warehouse/movement date/source sequence.

**Important columns:** Product/warehouse/date and four unit-role IDs; opening/received/issued/closing quantities; `recorded_delta_qty`, source row, segment ID/start, continuity/negative/UNKNOWN flags.

**Output:** `fct_inventory_daily_observed`

**Business rules:** Product, warehouse, movement_date and all unit roles reference the conformed dimensions. Only received/issued/delta are additive flows in compatible product/unit scopes. Opening/closing are balances, not flow measures. Preserve RETURN/UNKNOWN/negative observations.

**How to modify it safely:** Keep one row per source movement and exact signed flows. Changing segment annotations requires rebuilding inventory ancestors; do not add balance repair or sales joins.

**Tests:** PK/source-grain uniqueness, preservation against staging, declared column types, all FKs, dimensional JOIN cardinality, balance and historical reconstruction regressions. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_inventory.yml](_inventory.yml).

### Model: `fct_inventory_daily_observed`

**Purpose:** Summarize each observed day and select one coherent final stock observation.

**Grain:** One (dataset_name,product_id,warehouse_id,observation_date). Materialization: **table**.

**Inputs:** [fct_inventory_movement](fct_inventory_movement.sql).

**Main logic:**

1. Compute the latest event timestamp within each observed day for ambiguity diagnostics.
2. GROUP BY the daily grain; aggregate all received/issued/delta flows, counts, segment/unit diversity and discontinuities.
3. Choose a complete tuple of movement ID/source sequence/time/closing/unit/segment using maximum source sequence.
4. Expose the chosen observation plus negative/discontinuity/latest-timestamp ambiguity flags.

**Important columns:** `observed_closing_quantity`, `stock_unit_id`, `last_inventory_movement_id`, `last_source_sequence`, `last_movement_at`, recorded daily flow sums, `movement_count`, discontinuity/ambiguity flags.

**Output:** DSS queries and analytical joins; no downstream SQL model is configured.

**Business rules:** FKs: product, warehouse, observation date and stock unit. No missing-date fill or carry-forward. Do not sum closing balances across dates; do not add opening/closing values from many movements. Latest timestamp is a quality check, not the ordering substitute.

**How to modify it safely:** Keep argMax fields in one tuple so they come from the same row. Reconcile old/new date groups, exact flows, units and flags after any grouping/selection change.

**Tests:** Daily unique grain, declared column types, all FKs/cardinality, inventory_daily_reconciliation and inventory_daily_quality, native tied-time/source-order fixture, read-only history/flow reconciliation. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_inventory.yml](_inventory.yml).

#### Daily closing example

Two same-day rows close at 12 (source sequence 10) and 10 (sequence 11). The daily closing is 10, with the second row's ID, time, unit and segment. Received/issued totals include both movements. The next day's closing is another balance; adding it to 10 is not a stock measure. If both rows tie at the latest timestamp with different closings, selection still follows source order and ambiguity is flagged.

Inventory YAML declares column types, but the reusable `matches_declared_schema` test is currently attached to Dimensions and the sales Fact only. Inventory acceptance relies on its existing preservation, arithmetic, grain, relationship and observation tests; this handover does not add tests or change those contracts.
