# Recorded sales Fact

This fact is the primary sales interface for DSS consumers. It is neither verified demand nor net sales and has no verified sales warehouse relationship. [Data semantics](../../../../../docs/data-semantics.md) explains supported aggregation; [_sales.yml](_sales.yml) lists all 57 fields and typed tests.

```bash
uv run --locked dbt build --select +fct_sales_line dim_product dim_unit dim_date --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

### Model: `fct_sales_line`

**Purpose:** Publish every recorded sales line and its governed conversion result as a stable table.

**Grain:** One sales_invoice_line_id; alternate unique (dataset_name,dataset_row_number). Materialization: **table**.

**Inputs:** [int_sales_quantity_converted](../../intermediate/sales/int_sales_quantity_converted.sql).

**Main logic:**

1. Read int_sales_quantity_converted with the selected mapping version.
2. Explicitly project all 57 upstream columns without JOIN, filtering, aggregation or recalculation.
3. Write a full MergeTree replacement sorted by dataset/product/sold date/sales line ID.

**Important columns:** Original quantity/unit, all recorded prices/discounts/fees/percentages, line/batch/invoice/cashier descriptors, product/date IDs, verified stock unit, conversion status/factor/quantity and mapping provenance.

**Output:** DSS queries and analytical joins; no downstream SQL model is configured.

**Business rules:** FKs: product_id → dim_product, sold_date → dim_date, unit_id and nullable verified_stock_unit_id → dim_unit. No warehouse FK. Sum original quantities only within compatible product/unit scope; converted sums must expose unresolved coverage. Percentages are not additive; fees are not certified invoice totals.

**How to modify it safely:** Keep all 57 names/order/types and NULLs; add new analytical outputs separately when possible. A projection change requires upstream/YAML/schema/preservation updates and regression; do not infer demand or alter financial formulas.

**Tests:** Grain/source-key uniqueness, preserves_source_rows, matches_declared_schema, all FK roles, dimensional_join_cardinality, sales_fact_semantics, native all-status fixture and Python marts failure tests. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_sales.yml](_sales.yml).
