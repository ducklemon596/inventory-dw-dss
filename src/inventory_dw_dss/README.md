# Python package

## Responsibilities

| Module | Role and boundary |
|---|---|
| [cli.py](cli.py) | Installed `inventory-dw-dss` entry point; routes `extract` and explicit `bootstrap` |
| [extraction.py](extraction.py) | Reads one PostgreSQL snapshot, stages/validates raw replacements, publishes them; no CSV or bootstrap imports |
| [oltp_ingestion](oltp_ingestion/README.md) | Optional pandas preparation and transactional OLTP initialization |
| [validation](validation/README.md) | Read-only export lineage and inventory reconciliation, invoked by script wrappers |

```bash
uv run --locked inventory-dw-dss --help
uv run --locked inventory-dw-dss extract --help
uv run --locked --group bootstrap inventory-dw-dss bootstrap --help
```

`extract --batch-size 20000` is the operational loading interface. The CLI validates a positive batch size and reports extraction errors with a nonzero status. Bootstrap dependencies are checked/imported only when explicitly selected. No source connection failure triggers automatic initialization.

## Extraction maintenance

`prepare_table()` stages and reconciles one table; `publish()` exchanges/renames prepared tables; `rollback_publication()` reverses acknowledged operations. `extract_incremental()` owns connections, snapshot/lock lifetime, report and cleanup. Keep imports and connection variables compatible with the CLI and validators.

Business transformations belong in dbt, not Python. Read-only validators share canonical serialization code because lineage fingerprints must agree exactly. Do not create another parser to reproduce analytical SQL. [Regression instructions](../../tests/README.md) cover publication unit tests and disposable integration failures.

## Extraction behavior

Run from the repository root after PostgreSQL and ClickHouse are healthy:

```bash
uv run --locked inventory-dw-dss extract --batch-size 20000
```

The extractor reads all 12 OLTP tables from one PostgreSQL `REPEATABLE READ READ ONLY` snapshot. It streams rows in batches. Sales lines use `sold_at` and inventory movements use `occurred_at` as independent inclusive watermarks read from their corresponding raw tables. An absent/empty raw table triggers a full initial read. The ten reference/header tables refresh fully on each extraction.

Raw columns are stored as PostgreSQL text values (`String`/`Nullable(String)`) to preserve source formatting and NULL distinctions. Each table is staged and reconciled in a temporary ClickHouse database, then published per table through exchange/rename. An extraction transaction, insert or validation failure keeps the existing raw table. Publication is atomic per table, not across all 12 tables; run extraction and dbt sequentially and withhold downstream release until the dbt build completes.

The event-time watermark is not CDC. Changes older than a table's watermark, late arrivals before that boundary and source deletions are not detected automatically. A row reread at the boundary is merged by its OLTP primary key. The operational report at `reports/raw_extraction.json` records each table's watermark, rows read, new/read-again keys, before/after raw counts and reconciliation status. A reread count is not a changed-row count.

`prepare_table()` constructs and validates one replacement; `publish()` exchanges/renames prepared tables; `rollback_publication()` reverses acknowledged operations; `extract_incremental()` owns connection, snapshot, writer lock, report and cleanup lifetime. Keep recovery behavior and raw schema checks together with these functions. See the [validation README](validation/README.md) for read-only lineage checks and [tests README](../../tests/README.md) for extraction failure regressions.
