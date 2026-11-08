# Reusable data-test macros

`unique_grain` finds duplicate composite keys. `preserves_source_rows` FULL OUTER JOINs source/target and compares every source field with explicit NULL checks. `matches_declared_schema` compares actual columns/types/order to YAML. `dimensional_join_cardinality` groups after all configured dimension joins and requires one joined row per Fact grain.

**Failure interpretation:** Inspect returned keys. Missing parent rows require separate relationship tests: LEFT JOIN cardinality alone deliberately retains orphans. These macros do not create ClickHouse enforced constraints.

```bash
uv run --locked dbt test --select fct_sales_line --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This tests existing relations; build them and their required parents first. Model selections include attached tests, including cross-model dependencies. Use the [full acceptance build](../../../../tests/README.md) after changes. Relevant schema YAML and native fixtures live beside [the models](../../models/README.md). Read generated failing SQL under `target/compiled/inventory_dw/` from the dbt project, not these source templates.
