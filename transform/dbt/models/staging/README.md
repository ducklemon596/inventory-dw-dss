# Staging models

Staging turns the 12 extracted OLTP tables into typed views with consistent business names. Every view retains one row per raw record. It normalizes field values without joining records or calculating business aggregates.

Raw tables are declared in [_sources.yml](_sources.yml), using their extracted column names and text types. [_staging.yml](_staging.yml) documents the actual output columns, analytical types and existing tests. Field-level definitions belong in those contracts; the model guides explain how to maintain the SQL:

| Folder | Models | Responsibility |
|---|---|---|
| [reference](reference/README.md) | Seven product/classification/location/unit/cashier views | Typed current catalog identities and labels |
| [sales](sales/README.md) | Invoice headers and sales lines | Recorded sales quantities, amounts and line attributes |
| [inventory](inventory/README.md) | Documents, batches and movements | Recorded inventory observations and optional lot information |

## Normalization and naming

Each model uses `cleaned` to trim source text and apply field-specific missing markers. Its final `SELECT` validates and casts values through the shared [normalization macros](../../macros/README.md). Required malformed values fail; optional missing values stay NULL. Optional numeric parsing is strict too: malformed numbers cannot silently become missing values.

IDs become positive `UInt32`; optional IDs retain missing values. Quantities and amounts use `Decimal(18,6)`, percentages use `Nullable(Decimal(9,4))` on a 0–100 scale, and event timestamps retain microseconds in `DateTime64(6)`. Narrower shift/price/print fields have separate range checks. The YAML provides the exact type of every field.

Missing markers depend on the field. Descriptions and catalog labels can recognize `-`, `null`, `none` and `n/a`; identifiers, business codes, original descriptions and source labels do not share a global replacement rule. Only approved categorical domains normalize case and spacing. Product codes and unit labels preserve their spelling.

For example, raw `sales_line.quantity` becomes `sold_quantity`, while `inventory_movement.stock_in` becomes `received_quantity`. These are typed recorded values. The derived receipt-minus-issue measure is added in Intermediate. Raw `source_row_number` becomes `dataset_row_number`; it retains the source association rather than being generated again.

## Run and edit

From the repository root after extraction:

```bash
uv run --locked inventory-dw-dss transform --select staging
```

Use a model name instead of `staging` for a local change, and `transform --test --select MODEL_NAME` through the public CLI to test an existing relation. [Normalization regression](../../../../tests/staging/README.md) covers malformed values beyond the normal source data.

When changing a parser, inspect every macro caller. When changing a projection, compare it with `_staging.yml` and rebuild affected descendants using the [dbt selection guide](../../README.md). Existing source-count, key, relationship and normalization tests protect source preservation. Row filtering, financial formulas, UOM decisions and inventory reconstruction belong in downstream layers.
