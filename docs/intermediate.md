# Intermediate models

The intermediate layer enriches recorded sales and inventory observations while preserving source meaning and lineage. Model schemas and dbt tests are maintained beside the SQL under `transform/dbt/models/intermediate/`.

## Sales

| Model | Grain | Behavior |
|---|---|---|
| `int_sales_lines_enriched` | One source sales line | Retains line values and adds invoice, product, unit, cashier and optional batch identifiers |
| `int_sales_daily_observed` | Product × observed date × original unit | Aggregates recorded quantities only for combinations present in the source |
| `int_product_stock_units` | Dataset × product | Exposes a stock unit only when source unit evidence is consistent across warehouses |
| `int_sales_quantity_converted` | One source sales line | Adds governed mapping status and converts only exact identity or approved factors |
| `int_sales_uom_coverage` | Dataset × product × original unit × mapping version | Reports line and quantity coverage without combining unlike units |

Sales have no confirmed completion/cancellation state. Models do not infer net sales, warehouse assignment or return matching. Missing dates and batches remain absent. Fees and percentages retain the source-recorded scope. UOM decisions and version controls are documented in [UOM governance](uom.md).

## Inventory

| Model | Grain | Behavior |
|---|---|---|
| `int_inventory_movements_enriched` | One inventory movement | Preserves quantities and classification; adds labels, recorded delta and quality flags |
| `int_inventory_ledger_ordered` | One inventory movement | Adds the prior observation within dataset/product/warehouse using verified export order |
| `int_inventory_segments` | One movement assigned to a continuity segment | Starts at the recorded opening after a gap and accumulates recorded receipts minus issues |
| `diag_inventory_ledger_discontinuities` | One observed gap | Exposes adjacent rows and description-based diagnostic labels |

Recorded change is `inbound_quantity - outbound_quantity`; movement type does not determine its sign. RETURN directions, UNKNOWN classifications, negative balances, zero-flow rows and all source movements are retained. No return is linked to sales, no missing day is created, and no balance is repaired.

## Limits and validation

The source order represents one verified export, not a POS-native event sequence or change-data-capture history. Gaps start locally anchored segments; their differences are diagnostics, not movements. Daily facts describe the last observed source-sequence row for each observed day and flag tied latest timestamps. They do not certify physical or available stock. Detailed grains, reconciliations and measured results are in [historical inventory](historical-inventory.md); source-order evidence is in [sequence integrity](source-sequence-integrity.md).
