# Reference evidence

- `sequence_passport_v2.json`: archived research evidence for one supplied export; not used by extraction, dbt or production tests.
- `uom_sku_coverage_tierA_only.csv`: earlier user-supplied v1 coverage summary for 182 SKUs.
- `uom/uom_conversion_mapping_v1.csv`: immutable supplied v1 pair-level mapping and evidence.
- `uom/uom_conversion_mapping_v2.csv`: immutable supplied v2 pair-level mapping and evidence.
- `uom/MAPPING_CHANGELOG.md`: version availability, source checksum and publishing rules.

The passport applies only to the original export vintage and is retained outside the source package for provenance. It is not loaded by the operational pipeline.

Keep the supplied UOM mapping snapshots intact. The v1/v2 pair-level mappings form the governed dbt seed; the older coverage-only CSV is evidence only and cannot authorize conversions. Tier B/C remain unapproved. See [UOM governance](../../transform/dbt/seeds/README.md) for version selection and coverage.
