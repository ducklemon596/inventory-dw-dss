# Dimensional marts: DSS interface

A star schema combines transaction/observation **Facts** with shared descriptive **Dimensions**. The current system has four conformed dimensions, three source-preserving facts and two replenishment facts for the DSS; [implemented relationships](../../../../docs/data-model.md) show their exact keys and typed schemas.

| Folder | Models | Consumer use |
|---|---|---|
| [dimensions](dimensions/README.md) | Product, warehouse, unit, date | Describe/group facts using stable source IDs and current catalog attributes |
| [sales](sales/README.md) | Sales line | Recorded original and supported converted quantities with financials and provenance |
| [inventory](inventory/README.md) | Movement and observed daily inventory | Recorded flows and coherent observed balances, with quality flags |
| [replenishment](replenishment/README.md) | Product daily position, replenishment snapshot | Dense dispensary/storeroom stock, point-in-time features and forward stockout labels for DSS models |

All nine are fully rebuilt MergeTree tables. Fact SQL does not JOIN dimensions to manufacture keys; relationship/cardinality tests enforce the analytical joins. Real source IDs remain source IDs. The only special member is `dim_unit.unit_id = 0` for unverified sales stock-unit evidence; see [unit semantics](dimensions/README.md#dim_unit). There is no sales warehouse FK.

[Data meanings](../../../../docs/data-semantics.md) are part of the consumer contract: do not sum daily closing across dates, fabricate missing days or replace unresolved conversion with zero. The replenishment facts are the exception by design: they carry ledger balances forward and treat days without movements as zero flow, with the rules listed in their guide. New DSS models should use `ref()` on these facts and define their own explicit grain without altering validated source facts. See [DSS handover](../../../../docs/dss-handover.md) for the current consumer interface.
