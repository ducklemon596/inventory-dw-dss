# DSS handover

The current warehouse consumer interface is the ClickHouse star schema: four dimensions and three facts. A separate [MMS backend and Streamlit demo](../src/inventory_dw_dss/mms/README.md) now supplies forecasting, risk inference, replenishment scenarios, evaluation and decision tracking. Production integration requires the [verified normalized export contract](mms-data-contract.md) and original HistGB bundle; the included demo is synthetic. Use the [data model](data-model.md) for grains and relationships and [data semantics](data-semantics.md) before interpreting measures.

## Current analytical interfaces

- `dim_product`, `dim_warehouse`, `dim_unit`, `dim_date` describe product, location, unit and calendar roles.
- `fct_sales_line` provides one preserved source line, its original measures and governed conversion results.
- `fct_inventory_movement` provides source movement detail and continuity diagnostics.
- `fct_inventory_daily_observed` provides observed daily balances at dataset × product × warehouse × date grain.

Sales have no warehouse relationship. Inventory daily rows are observations, not a dense calendar or guaranteed stock availability. Historical inventory and UOM rules are preserved; new DSS outputs should be built as separate dbt models with explicit grains.

## Where to work

| Concern | Maintained code guide |
|---|---|
| Operational source and extraction | [Python package](../src/inventory_dw_dss/README.md) |
| Optional one-time CSV-to-OLTP bootstrap | [Bootstrap package](../src/inventory_dw_dss/oltp_ingestion/README.md) |
| Staging types and normalization | [Staging models](../transform/dbt/models/staging/README.md) |
| Reusable sales and inventory logic | [Intermediate models](../transform/dbt/models/intermediate/README.md) |
| DSS-facing facts and dimensions | [Marts models](../transform/dbt/models/marts/README.md) |
| Governed conversion references | [dbt seed](../transform/dbt/seeds/README.md) |
| Tests and regression procedures | [Test guide](../tests/README.md) |

The code READMEs are authoritative for commands, configurations, dependencies, model inputs/outputs and safe editing procedures. System-level meanings and limitations remain in this documentation set.
