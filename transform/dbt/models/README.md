# Model map

Models form a directed dependency graph through `source()` and `ref()`. Read the [dbt guide](../README.md) for execution and the [semantics reference](../../../docs/data-semantics.md) before combining measures.

| Layer | Responsibility | Models and maintenance instructions |
|---|---|---|
| Staging | One typed, consistently named row per raw record | [12 views](staging/README.md) |
| Sales Intermediate | Reusable enrichment, observed grouping, stock-unit evidence and approved conversion | [Five views](intermediate/sales/README.md) |
| Inventory Intermediate | Enrichment, verified order, continuity segments and diagnostics | [Two tables and two views](intermediate/inventory/README.md) |
| Replenishment Intermediate | Daily flow roles and dense carried-forward stock position | [One view and one table](intermediate/replenishment/README.md) |
| Marts | Conformed dimensions, stable facts and DSS replenishment inputs | [Four Dimensions / five Facts](marts/README.md) |

Each domain README documents every model's purpose, grain, inputs, main logic, important columns, output, business rules, safe modification steps and tests. YAML beside SQL is the complete column/type/test contract. Model names remain stable despite directory grouping.

Place new reusable business calculations in Intermediate; place new DSS-specific outputs in a clearly named subfolder of Marts only when needed. A directory is not a reason to invent a new model. Keep source preservation, UOM rules and inventory reconstruction unchanged unless a reviewed requirement supplies stronger evidence.
