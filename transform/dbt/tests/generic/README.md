# Reusable data-test macros

`unique_grain` finds duplicate composite keys. `preserves_source_rows` FULL OUTER JOINs source/target and compares every source field with explicit NULL checks. `matches_declared_schema` compares actual columns/types/order to YAML. `dimensional_join_cardinality` groups after all configured dimension joins and requires one joined row per Fact grain.

**Failure interpretation:** Inspect returned keys. Missing parent rows require separate relationship tests: LEFT JOIN cardinality alone deliberately retains orphans. These macros do not create ClickHouse enforced constraints.

```bash
uv run --locked inventory-dw-dss transform --test --select fct_sales_line
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
