# Pipeline CLI and ClickHouse raw loading

The installed entrypoint is `inventory-dw-dss`, declared in [pyproject.toml](../../pyproject.toml). It exposes two operation families: `load <destination>` and `transform`. Commands parse and validate arguments before importing destination-specific dependencies.

| Task | Recommended guide |
|---|---|
| Optional source CSV → PostgreSQL | [PostgreSQL loader](oltp_ingestion/README.md) |
| PostgreSQL → ClickHouse raw | Commands below |
| ClickHouse raw → dbt marts/tests | [Transformations](../../transform/dbt/README.md) |

## ClickHouse raw prerequisites

PostgreSQL must contain all 12 supported `oltp` tables; ClickHouse must be healthy. [Service configuration](../../infra/README.md) lists connection defaults and environment variables. Extraction reads PostgreSQL only and does not import pandas or read CSVs. Run commands from the repository root so the extraction receipt is written under its `reports/` directory.

## Routine incremental load

```bash
uv run --locked inventory-dw-dss load raw
```

For `sales_line`, read rows with `sold_at >= max(raw.sold_at)`; inventory uses its independent `occurred_at` watermark. Empty/missing raw transaction tables cause an initial all-source read. Timestamps retain microseconds. Ten reference/header tables refresh fully each time.

The inclusive boundary deliberately rereads the latest timestamp. Transactions merge by OLTP PK, so repeated reads replace matching keys without duplicate rows. Other existing transactions remain present. PostgreSQL reads are bounded; ClickHouse still copies its existing raw transaction rows locally when building the reconciled replacement.

## Full load

```bash
uv run --locked inventory-dw-dss load raw --full
```

Read all PostgreSQL transactions and merge by PK, including historical values outside the current watermark. All reference/header records refresh, including source deletions. Retained transactions whose referenced header was deleted can fail dbt relationships and require source review. This is an all-source merge, not truncate or deletion synchronization: a transaction removed from PostgreSQL remains in raw until an independently reviewed removal procedure is applied.

## Time-range load

```bash
uv run --locked inventory-dw-dss load raw --start 2023-01-01 --end 2023-01-31
```

Both endpoints are inclusive `YYYY-MM-DD` event dates. Transactions are read with `timestamp >= start midnight AND timestamp < midnight after end`, independently of current raw watermarks. Matching PKs update; existing rows outside the range stay present. A subsequent transform processes all retained raw history, not only this read window. All ten reference/header tables still refresh completely. An empty transaction range succeeds and preserves current transactions while refreshing references.

Use explicit full/range commands for a deliberate replay of older records. Routine event-time loading does not automatically discover late records, changes before the watermark, backward-moved timestamps or source deletions. A range selects the source's current timestamp; it cannot identify a removed row.

```bash
uv run --locked inventory-dw-dss load raw --help
```

`--full` cannot be combined with dates. Missing/reversed/invalid date endpoints fail before a connection is opened. Batch size defaults internally to 20,000; operational users do not need to configure it.

## Publication, reports and maintenance

All PostgreSQL queries share one `REPEATABLE READ READ ONLY` snapshot and a session advisory lock serializes writers to the same raw destination. Raw columns retain canonical PostgreSQL text as `String`/`Nullable(String)`. Deltas, merged counts and PK uniqueness are validated in a temporary `_extract_*` database before publication.

Existing tables publish by atomic exchange per table. Publication across all tables is not one transaction. A caught publication error reverses acknowledged steps; recovery tables are retained when an exchange result is ambiguous. Inspect the receipt and table names/UUIDs before retrying an ambiguous publication; do not blindly delete its work database.

`reports/raw_extraction.json` records mode (`incremental`, `full` or `range`), selected dates, per-table watermark, read/new/reread counts, final raw counts and reconciliation/recovery status. Reread counts include changed and unchanged values. The report is replaced each run.

[extraction.py](extraction.py) owns `load_raw()`, `prepare_table()`, publication and rollback. [cli.py](cli.py) owns scope validation and delegates `transform` to the installed dbt runner using repository project/profile paths. UOM version defaults to the fixed project variable; `--uom-version` selects another published version. Business calculations remain in dbt. [Tests](../../tests/README.md) cover the public CLI and disposable destination databases.

Run raw loading and transformations sequentially. Release marts to DSS consumers only after the complete transform succeeds.
