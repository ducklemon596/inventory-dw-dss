# Inventory facts

The two full-rebuild MergeTree tables expose recorded movements and daily closing observations. [_inventory.yml](_inventory.yml) is the field/type/test reference. [Inventory Intermediate](../../intermediate/inventory/README.md) owns source ordering, continuity gaps and segment reconstruction.

## fct_inventory_movement

[SQL](fct_inventory_movement.sql) projects `int_inventory_segments` at one row per `inventory_movement_id`, retaining alternate lineage key `(dataset_name, dataset_row_number)`. It explicitly selects 36 fields: transaction/source identities, event/product/location, recorded labels and quantities, four unit roles, receipt-minus-issue delta, segment membership and quality flags.

The fact preserves source flows and balances. Continuity gaps remain diagnostic; they are not added to receipts or issues. All movements survive, including RETURN, UNKNOWN and negative closing observations. Its direct model consumer is `fct_inventory_daily_observed`.

Analytical joins use `dim_product`, `dim_warehouse`, four roles of `dim_unit` and `dim_date` through `movement_date`. Fact SQL itself does not join dimensions. Existing source-preservation, balance, dimensional cardinality and relationship tests check that each source movement remains represented once.

## fct_inventory_daily_observed

[SQL](fct_inventory_daily_observed.sql) reads the movement fact at `(dataset_name, product_id, warehouse_id, observation_date)` grain. `observations` identifies the latest event timestamp within a day for ambiguity diagnostics. `daily` aggregates all movement flows and selects one complete final observation tuple using the maximum source row number.

Its 21 fields include the daily keys; selected closing quantity/unit/movement/time/segment; first/last source sequence; received/issued/delta sums; movement/gap/segment/unit counts; and discontinuity, negative-closing and latest-time ambiguity flags. Selected closing fields come from the same source row. Unobserved dates remain absent.

Consumers join product, warehouse, closing-stock unit and calendar date dimensions. No downstream dbt model is currently configured. For example, same-day source rows 10 and 11 closing at 12 and 10 produce a daily observed closing of 10, with row 11's identity/time/unit/segment. Both movements contribute to flows. Equal latest timestamps with different closings set the ambiguity flag; selection still follows source sequence.

Daily closing is a balance, so adding it across dates is not a stock measure. Missing dates are not zero stock, and observed closing does not certify physical or available stock. Existing daily reconciliation/quality, exact grain, relationships and join-cardinality tests verify these rules, with a native tied-time fixture.

## Run and modify

From the repository root:

```bash
uv run --locked inventory-dw-dss transform --select +fct_inventory_daily_observed dim_product dim_warehouse dim_unit dim_date
```

This selects the inventory ancestors and logical dimension roles. Use the complete build to include sales and diagnostics for acceptance; inventory unit evidence also influences sales conversion. The [dbt guide](../../../README.md) explains testing existing relations and selecting changed descendants.

Keep one movement per source ID, exact quantity arithmetic and complete-tuple daily selection. A source-order, segment or grouping change affects persisted inventory outputs and must pass predecessor, anchor, reconstruction and daily tests together. Full business interpretation is in [data semantics](../../../../../docs/data-semantics.md).
