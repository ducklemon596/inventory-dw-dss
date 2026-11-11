# Intermediate models

Intermediate models combine typed Staging records into reusable business transformations. They do not change source quantities. Only the replenishment branch derives positions for unobserved days, under documented ledger rules.

- [Sales](sales/README.md): enrichment, original-unit daily sales, verified stock-unit evidence, governed conversion and coverage.
- [Inventory](inventory/README.md): movement enrichment, source-order predecessors, continuity segments and gap diagnostics.
- [Replenishment](replenishment/README.md): daily flow roles and a dense stock position that carries balances forward under explicit ledger rules.

The default is a view; ordered ledger, segments and the dense daily position explicitly use full-rebuild MergeTree tables. Inventory is sequenced by dataset/product/warehouse/source row. Sales has no warehouse assignment, but conversion evidence inspects inventory units across warehouses. That dependency is important when selecting a sales rebuild.

Follow the model-level rules in each domain and the [DSS handover](../../../../docs/dss-handover.md). Never use timestamp-tail filtering to simplify historical dependencies. [dbt tests](../../tests/README.md) validate preservation, arithmetic and conversion restrictions.
