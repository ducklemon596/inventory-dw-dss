# Read-only validation utilities

[source_sequence.py](source_sequence.py) compares the verified export across CSV, prepared CSV, PostgreSQL, raw, staging and enriched Intermediate rows. It checks key associations, fingerprints, sequence sets and ledger transitions. [inventory_history.py](inventory_history.py) first verifies the stock passport fingerprint, then checks ledger/segment/movement/daily metrics and exact per-unit flows.

These modules issue database SELECTs only. They can write the requested local JSON report. They do not prepare data, extract, build models or repair failed records. [Script entry points](../../../scripts/README.md) provide the commands; run them while extraction and dbt are idle.

## Inputs and failure interpretation

- Passport: [sequence_passport_v2.json](../../../data/reference/sequence_passport_v2.json), specific to one export.
- Source validator: original CSVs and existing monthly prepared partitions/manifest must be present. Changed/missing checksums stop validation; it does not regenerate evidence.
- History validator: needs current staging and inventory tables plus a matching passport. A new export requires newly reviewed evidence; do not change expected counts to hide a mismatch.
- Database environment: same PG/ClickHouse settings as [infra](../../../infra/README.md).

Maintain canonical field order, decimal/text serialization and source business-key mapping. Generated OLTP IDs are checked for association but are not passport business IDs or the inventory ordering key. Tests in [tests/validation](../../../tests/validation/README.md) protect serializer and reconciliation failure behavior.
