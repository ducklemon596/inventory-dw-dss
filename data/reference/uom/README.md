# Immutable UOM references

The v1 and v2 CSVs preserve supplied pair-level approvals and evidence byte-for-byte. Their exact union is loaded through the [dbt seed](../../../transform/dbt/seeds/README.md). [MAPPING_CHANGELOG.md](MAPPING_CHANGELOG.md) is the authoritative version/checksum/publication record. The older SKU coverage file one directory above is evidence only, not a source of factors.

Never edit these published files, normalize their labels or replace candidate factors with approved factors. A new approved decision belongs to a new immutable version with provenance/checksum, appended seed rows and explicit contract tests. [Governance](../../../transform/dbt/seeds/README.md) gives the procedure and meaning of coverage. [Reference unit tests](../../../tests/uom/test_reference.py) protect both checksums and exact seed union.
