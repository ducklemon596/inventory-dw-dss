# Intermediate reconciliation

Sales tests compare enrichment and original-unit daily grouping with source rows. Inventory tests check opening + received - issued = closing, exact predecessor identity/sequence/units, segment anchors/ranges/cumulative reconstruction and complete discontinuity diagnostics. Generic preservation compares all parent fields, including NULL distinctions.

**Failure interpretation:** Inspect the exact dataset/product/warehouse ledger in source order. A real discontinuity is retained, not automatically repaired. An arithmetic/preservation failure is different from an expected gap flag.

```bash
uv run --locked dbt test --select int_inventory_segments int_sales_lines_enriched --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This tests existing relations; build them and their required parents first. Model selections include attached tests, including cross-model dependencies. Use the [full acceptance build](../../../../tests/README.md) after changes. Relevant schema YAML and native fixtures live beside [the models](../../models/README.md). Read generated failing SQL under `target/compiled/inventory_dw/` from the dbt project, not these source templates.
