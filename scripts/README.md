# Validation entry points

These scripts call reusable modules in `src/inventory_dw_dss/validation/`.
They issue SELECT queries only and write an optional local JSON report.
They do not prepare CSV, load OLTP, extract data or build dbt models.

```bash
uv run --locked python scripts/validation/validate_source_sequence.py --output reports/source_sequence.json
uv run --locked python scripts/validation/validate_inventory_history.py --output reports/historical_inventory.json
```

The source validator checks original/prepared CSV through OLTP, raw, staging and inventory/sales
enrichment. The historical validator checks the stock passport fingerprint before comparing
its snapshot-specific counts with ledger, segment and inventory facts. Build dbt first.
Default reference: `data/reference/sequence_passport_v2.json`. Database settings match extraction.
Run validation while extraction and dbt are idle so relations do not change during reads.

Add reusable logic to the package and keep wrappers here short. See
[source evidence](../docs/source-system.md) and
[historical inventory](../docs/data-semantics.md) for interpretation and limitations.
