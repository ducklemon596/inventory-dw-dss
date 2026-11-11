# Reference data

- `uom/uom_conversion_mapping_v1.csv`, `uom/uom_conversion_mapping_v2.csv`: immutable pair-level unit-of-measure mappings with evidence. Together they form the governed dbt seed.
- `uom/MAPPING_CHANGELOG.md`: version availability, source checksums and publishing rules.

Keep the mapping snapshots byte-identical; tests check their checksums. Tier B/C pairs remain unapproved. See [UOM governance](../../transform/dbt/seeds/README.md) for version selection and coverage.
