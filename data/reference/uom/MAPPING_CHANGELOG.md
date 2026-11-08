# UOM mapping versions

The official seed is the exact 397-row union of the two supplied immutable snapshots.
Keys are `(mapping_version, product_id, sales_unit)`; product_id is POS DrugCode.

## uom_mapping_v2_2026-11-08

Supplied as `uom_conversion_mapping.csv`; retained as `uom_conversion_mapping_v2.csv`
without changing bytes.

- 207 pairs, 197 DrugCodes: 87 approved, 89 candidate, 31 quarantined.
- SHA-256: `7e2e0c0e51dda3e96e5466af664d40ae4a4129d10171eb60af46bc0c55ba0aa2`.
- Compared with authentic v1: 17 additional pairs across 15 SKUs, comprising 14 approved,
  two candidate and one quarantined pair. No pairs removed.
- All 190 existing pair decisions and evidence fields are unchanged, except mapping_version.
- Default development version; production should still pin it explicitly.

## uom_mapping_v1_2026-11-08

Supplied as `uom_conversion_mapping_v1.csv`; retained under the same filename here,
without changing bytes. It was appended to the seed after the original v2 integration.

- 190 pairs, 182 DrugCodes: 73 approved, 87 candidate, 30 quarantined.
- SHA-256: `a9b4655cc04113bc1605fc06694ea43efa827032ddd7a3910a30ee83324f787c`.
- Historical decisions are preserved; they are not relabeled or expanded to resemble v2.

## Publishing

Every row retains the supplied invoice evidence, ratios, price-check flag and factors.
Tier A approval is explicit; a failed price check does not revoke a supplied approval.
The research skeleton and original research changelog were not supplied; this file records
verified integration provenance and the actual snapshot diff.

Published snapshots are immutable. New approvals require a new version and a separately
retained source CSV with provenance and checksum. Append its rows to the seed, preserving
all existing version/product/sales-unit rows and exact evidence. Add its contract counts
and immutable checksum test, then validate both the new and existing versions independently.

Explicitly pin `uom_mapping_version` during deployment. An absent version fails validation;
there is no fallback. Candidate factors never authorize conversion. Neither product-code
casing nor differing unit labels are normalized or treated as equivalent.
