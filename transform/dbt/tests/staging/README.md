# Staging validation

`normalized_values` reads every projection to exercise optional casts and string guards; source counts detect lost/duplicated rows. Source-key tests and batch/product natural/association checks protect identity and optional batch correctness. Declared not-null, unique and relationship tests complement these checks.

**Failure interpretation:** Investigate the raw value and source PK first. Parser failures should remain visible; a missing optional value is different from malformed nonempty text.

```bash
uv run --locked dbt test --select staging --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This tests existing relations; build them and their required parents first. Model selections include attached tests, including cross-model dependencies. Use the [full acceptance build](../../../../tests/README.md) after changes. Relevant schema YAML and native fixtures live beside [the models](../../models/README.md). Read generated failing SQL under `target/compiled/inventory_dw/` from the dbt project, not these source templates.
