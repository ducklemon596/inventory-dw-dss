# UOM governance and conversion

Tests enforce selected version existence, published counts/domains, unique version/code/unit pairs, compatible verified stock targets, approved-only arithmetic, exact quantity preservation and exhaustive coverage partitions. Unit fixtures check statuses, exact signed decimals, version isolation and cross-warehouse evidence.

**Failure interpretation:** Check version pin and immutable source, then exact business-code/unit match and stock evidence. Candidate/quarantined numeric evidence is not authorization. A new version needs explicit reviewed publication contracts.

```bash
uv run --locked dbt test --select int_sales_quantity_converted int_product_stock_units int_sales_uom_coverage --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This tests existing relations; build them and their required parents first. Model selections include attached tests, including cross-model dependencies. Use the [full acceptance build](../../../../tests/README.md) after changes. Relevant schema YAML and native fixtures live beside [the models](../../models/README.md). Read generated failing SQL under `target/compiled/inventory_dw/` from the dbt project, not these source templates.
