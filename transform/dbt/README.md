# dbt transformations

The `inventory_dw` project reads ClickHouse `raw` tables populated from PostgreSQL OLTP. Run dbt locally through `uv` after extraction.

| Path | Responsibility |
|---|---|
| `models/staging/` | Source-shaped typed views grouped by sales, inventory and reference domains |
| `models/intermediate/sales/` | Sales enrichment, observed daily sales, stock-unit evidence and governed conversion |
| `models/intermediate/inventory/` | Movement enrichment, source-ordered ledger, continuity segments and gap diagnostics |
| `models/marts/inventory/` | Recorded movement and daily observed inventory facts |
| `seeds/` | Versioned governed UOM decisions |
| `tests/` | Source preservation, grain, reconciliation and business invariants |
| `analyses/` | UOM coverage measurements |
| `macros/` | Shared normalization and mapping-version validation |

```bash
uv run --locked dbt seed --select uom_conversion_mapping --project-dir transform/dbt --profiles-dir transform/dbt
uv run --locked dbt build --project-dir transform/dbt --profiles-dir transform/dbt \
  --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

Models retain their dbt names when SQL files are organized into domain folders. Inventory ledger, segment and fact tables rebuild on each run; enrichment and diagnostics are views. No incremental historical maintenance is configured. `target/` and `logs/` are generated outputs ignored by Git. Read [UOM governance](../../docs/uom.md) before publishing a new mapping version.
