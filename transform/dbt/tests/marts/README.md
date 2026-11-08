# Fact and Dimension checks

Calendar tests check event coverage, complete dates and ISO/civil attributes; product labels use NULL-aware comparisons. Sales checks preserve version/status/NULL restrictions. Daily inventory reconciles exact flow sums, observed grains, selected complete last-row tuples and quality flags. YAML adds all FK roles, uniqueness, preservation and dimensional JOIN cardinality; exact schema checks are attached to the four Dimensions and sales Fact.

**Failure interpretation:** Trace wrong values through Fact → Intermediate → Staging → Raw. Identify missing parents, duplicate dimensions, mismatched grain or stale tables; do not remove an FK/cardinality check merely because a LEFT JOIN returns rows.

```bash
uv run --locked dbt test --select fct_sales_line fct_inventory_movement fct_inventory_daily_observed dim_product dim_date --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This tests existing relations; build them and their required parents first. Model selections include attached tests, including cross-model dependencies. Use the [full acceptance build](../../../../tests/README.md) after changes. Relevant schema YAML and native fixtures live beside [the models](../../models/README.md). Read generated failing SQL under `target/compiled/inventory_dw/` from the dbt project, not these source templates.
