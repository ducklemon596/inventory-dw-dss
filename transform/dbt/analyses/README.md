# UOM coverage analyses

These SQL analyses inspect existing views; they do not materialize additional models.

| Analysis | Meaning |
|---|---|
| [uom_coverage_summary](uom_coverage_summary.sql) | Version-specific line/status counts, known conversion-needed pairs and SKU coverage |
| [uom_coverage_measurement](uom_coverage_measurement.sql) | Covered absolute original quantity percentage per dataset/product/original unit |

```bash
uv run --locked dbt show --select uom_coverage_summary --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
uv run --locked dbt show --select uom_coverage_measurement --limit 20 --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

Build the conversion branch with the same version first: an analysis variable does not change an existing view's pinned literal. Row-, pair-, SKU- and quantity-weighted coverage are different metrics. Do not aggregate product/unit quantities into one global denominator. A zero denominator returns missing percentage. [Sales models](../models/intermediate/sales/README.md) explain classifications and retained NULLs.
