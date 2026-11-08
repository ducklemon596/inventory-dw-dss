# Intermediate models

Intermediate models combine typed Staging records into reusable business transformations. They do not change source quantities or manufacture missing observations.

- [Sales](sales/README.md): enrichment, original-unit daily sales, verified stock-unit evidence, governed conversion and coverage.
- [Inventory](inventory/README.md): movement enrichment, source-order predecessors, continuity segments and gap diagnostics.

The default is a view; ordered ledger and segments explicitly use full-rebuild MergeTree tables. Inventory is sequenced by dataset/product/warehouse/source row. Sales has no warehouse assignment, but conversion evidence inspects inventory units across warehouses. That dependency is important when selecting a sales rebuild.

Follow the model-level rules in each domain and the [DSS handover](../../../../docs/dss-handover.md). Never use timestamp-tail filtering to simplify historical dependencies. [dbt tests](../../tests/README.md) validate preservation, arithmetic and conversion restrictions.
