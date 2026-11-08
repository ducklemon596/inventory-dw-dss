# Reference evidence

- `sequence_passport_v2.json`: user-supplied export fingerprint and snapshot diagnostic baselines.
- `uom_sku_coverage_tierA_only.csv`: earlier user-supplied v1 coverage summary for 182 SKUs.
- `uom/uom_conversion_mapping_v1.csv`: immutable supplied v1 pair-level mapping and evidence.
- `uom/uom_conversion_mapping_v2.csv`: immutable supplied v2 pair-level mapping and evidence.
- `uom/MAPPING_CHANGELOG.md`: version availability, source checksum and publishing rules.

The passport bytes are unchanged from the supplied file (SHA-256
`4ac3d5ac0675cfd62d335641dc675221f43000cff0cb836bec509b21d4087705`).
Its counts apply only to the verified export; row sequence is not a source-native clock.
The CSV reports 68 fully convertible, four partially convertible and 110 unresolved SKUs,
with 73 approved pairs counted. It does not contain the actual unit pairs, factors,
approval evidence or mapping vintage, so it cannot authorize or execute conversions.

Keep these original references intact. The supplied v1/v2 pair-level mappings form the governed
397-row dbt seed; the older coverage-only CSV remains evidence and is never used as factors. Tier B/C
remain unapproved. See [UOM governance](../../docs/uom.md) for version selection and coverage.
