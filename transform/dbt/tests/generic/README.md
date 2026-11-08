# Reusable data-test macros

`unique_grain` finds duplicate composite keys. `preserves_source_rows` FULL OUTER JOINs source/target and compares every source field with explicit NULL checks. Only reviewed representation changes may use `column_overrides` (SQL expressions against alias `expected`); every other source field still receives exact NULL-aware comparison. `excluded_primary_keys` removes only explicitly reserved target dimension rows from source matching; a separate special-member contract must validate their presence, label and source-key non-collision. Current uses are the sales stock-unit NULL-to-0 projection and the reserved unit row.

`matches_declared_schema` compares actual columns/types/order to YAML. `dimensional_join_cardinality` groups after all configured dimension joins and requires one joined row per Fact grain.

**Failure interpretation:** Inspect returned keys. Missing parent rows require separate relationship tests: LEFT JOIN cardinality alone deliberately retains orphans. These macros do not create ClickHouse enforced constraints.

```bash
uv run --locked inventory-dw-dss transform --test --select fct_sales_line
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
