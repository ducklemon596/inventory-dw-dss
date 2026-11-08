# Recorded sales fact

[fct_sales_line.sql](fct_sales_line.sql) publishes one row per `sales_invoice_line_id`, with alternate lineage key `(dataset_name, dataset_row_number)`. Its only input is `int_sales_quantity_converted`. The full output contract is in [_sales.yml](_sales.yml).

The model explicitly projects all 57 input columns in the same order and types. It adds no calculation or dimension join. Original quantities, recorded monetary fields, optional batch/shift descriptions, conversion status, selected version, applied factor and evidence remain together on each line. Identity/approved quantities are retained; unresolved conversion remains NULL.

Consumers join `dim_product` by `product_id`, `dim_unit` by the original or verified unit role, and `dim_date` by `sold_date = calendar_date`. Invoice and cashier remain line descriptors. There is no warehouse FK and no downstream dbt model configured; DSS models can depend on this fact through `ref()`.

For example, a line recording `2 Box` retains that original quantity/unit even when an approved mapping also provides 20 Tab. An unresolved mapping keeps the original sale usable while exposing a missing converted quantity. [Sales Intermediate](../../intermediate/sales/README.md) owns the conversion rules; [data semantics](../../../../../docs/data-semantics.md) explains aggregation and monetary scope.

Run from the repository root:

```bash
uv run --locked inventory-dw-dss transform --select +fct_sales_line dim_product dim_unit dim_date
```

For existing relations, add `--test` and select `fct_sales_line`. Existing tests check all 57 values against the upstream model, exact schema, source grain, dimensional relationships/join cardinality and UOM semantics. The native fixture includes signed quantities, zero amounts and conversion outcomes; [mart regression](../../../../../tests/marts/README.md) checks that contract violations are rejected.

Edit a reusable calculation in Intermediate first. If a reviewed requirement changes the fact projection, update its SQL, YAML and source-preservation/schema tests together, then rebuild affected parents and consumers. Source changes to stock-unit evidence or mapping version can also invalidate persisted sales results.
