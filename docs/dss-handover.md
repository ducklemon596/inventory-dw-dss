# DSS handover

The current consumer interface is the ClickHouse star schema: four dimensions, three source-preserving facts and two replenishment facts built for DSS models. The [MMS backend and Streamlit app](../src/inventory_dw_dss/mms/README.md) reads the replenishment facts for forecasting, risk inference, replenishment scenarios, evaluation and decision tracking. Use the [data model](data-model.md) for grains and relationships and [data semantics](data-semantics.md) before interpreting measures.

## Current analytical interfaces

- `dim_product`, `dim_warehouse`, `dim_unit`, `dim_date` describe product, location, unit and calendar roles.
- `fct_sales_line` provides one preserved source line, its original measures and governed conversion results.
- `fct_inventory_movement` provides source movement detail and continuity diagnostics.
- `fct_inventory_daily_observed` provides observed daily balances at dataset × product × warehouse × date grain.
- `fct_product_daily_position` provides a dense daily stock position per product, split into dispensary and storeroom balances, with flow roles and sales value.
- `fct_product_replenishment_snapshot` provides point-in-time features (MA90 demand, days of supply, receipt and stockout history, eligibility) and forward 7/14/30-day stockout and sales labels per product and decision date.

## Using the replenishment facts

Read features and labels from `fct_product_replenishment_snapshot`. Filter the decision cohort with `is_orderable = 1`, and for incident-stockout risk also `dispensary_on_hand_qty > 0`. Exclude rows whose label is NULL (window past the export end) and, for evaluation, optionally rows with `label_window_has_stocktake_{h}d = 1`. Quantities share the product's stock unit; use `unit_sales_value_90d` to express budgets in currency. The [replenishment guide](../transform/dbt/models/marts/replenishment/README.md) lists the business rules and column groups.

Sales have no warehouse relationship. Inventory daily rows are observations, not a dense calendar or guaranteed stock availability. Historical inventory and UOM rules are preserved; new DSS outputs should be built as separate dbt models with explicit grains.

## Where to work

| Concern | Maintained code guide |
|---|---|
| Operational source and extraction | [Python package](../src/inventory_dw_dss/README.md) |
| Optional one-time CSV-to-OLTP bootstrap | [Bootstrap package](../src/inventory_dw_dss/oltp_ingestion/README.md) |
| Staging types and normalization | [Staging models](../transform/dbt/models/staging/README.md) |
| Reusable sales and inventory logic | [Intermediate models](../transform/dbt/models/intermediate/README.md) |
| DSS-facing facts and dimensions | [Marts models](../transform/dbt/models/marts/README.md) |
| MMS training and evaluation on pharmacy data | [Real-data evaluation](mms-real-data-evaluation.md) |
| Dense position, DSS features and labels | [Replenishment marts](../transform/dbt/models/marts/replenishment/README.md) |
| Governed conversion references | [dbt seed](../transform/dbt/seeds/README.md) |
| Tests and regression procedures | [Test guide](../tests/README.md) |

The code READMEs are authoritative for commands, configurations, dependencies, model inputs/outputs and safe editing procedures. System-level meanings and limitations remain in this documentation set.
