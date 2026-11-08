# Fact and Dimension checks

Calendar tests check event coverage, complete dates and ISO/civil attributes; product labels use NULL-aware comparisons. Sales checks preserve version/status/NULL restrictions. Daily inventory reconciles exact flow sums, observed grains, selected complete last-row tuples and quality flags. YAML adds all FK roles, uniqueness, preservation and dimensional JOIN cardinality; exact schema checks are attached to the four Dimensions and sales Fact.

**Failure interpretation:** Trace wrong values through Fact → Intermediate → Staging → Raw. Identify missing parents, duplicate dimensions, mismatched grain or stale tables; do not remove an FK/cardinality check merely because a LEFT JOIN returns rows.

```bash
uv run --locked inventory-dw-dss transform --test --select fct_sales_line fct_inventory_movement fct_inventory_daily_observed dim_product dim_date
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
