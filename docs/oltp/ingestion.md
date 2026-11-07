# OLTP ingestion

This upstream workflow reconstructs or incrementally updates PostgreSQL from `data/raw/sales_raw.csv` and `data/raw/stock_raw.csv`. It is separate from DW execution. Commands run from the repository root; use `--root /path/to/checkout` when running elsewhere.

## Preparation

```bash
uv run --group bootstrap inventory-dw-dss bootstrap prepare --interval 1mo
```

Pandas reads chunks (default 100,000 rows), preserving source codes, raw columns and RowNumber. It splits timestamps, shifts, batches/expiry, price tiers, percentage values, stock quantities/units and recognized stock descriptions. Optional parse failures retain the row, leave derived fields empty and record warnings. Invalid source keys, partition timestamps or required numeric values fail preparation.

| Interval | Boundaries |
|---|---|
| `1d` | Calendar day |
| `3d` | Three-day windows anchored at 2023-01-01 |
| `1w` | Monday–Sunday |
| `1mo` | Calendar month, default |

Files go to `data/processed/<interval>/<dataset>/`, for example `sales/sales_2023-01-01_2023-01-31.csv`. Only nonempty partitions are written, ordered by timestamp and RowNumber. The manifest records schema version, source/partition checksums, row counts and warnings. Publication replaces a complete set under a file lock; failed preparation retains the preceding complete set. Running preparation never appends duplicate source rows.

Existing partitions remain usable after repository restructuring. Their manifest source paths record where the raw files were originally prepared; the loader validates schema, partition checksums and counts rather than reopening those original source paths. New preparation records `data/raw/` paths.

## Incremental loading

```bash
uv run --group bootstrap inventory-dw-dss bootstrap load --interval 1mo --all
uv run --group bootstrap inventory-dw-dss bootstrap load --interval 1mo \
  --from 2023-01-01 --to 2023-01-31 --dataset both
```

`--dataset` is `sales`, `stock` or `both` (default). Supply `--all` or both inclusive date endpoints. A date range cutting across a partition loads only matching rows. Loading never runs preparation implicitly.

The loader starts the PostgreSQL container if required and uses its `psql`; no host PostgreSQL client or exposed host port is needed. In one transaction, an advisory lock serializes loads, the complete idempotent schema is applied, selected rows COPY into temporary tables, catalogs/batches resolve, and details upsert by `(source_dataset, source_row_number)`. The namespace is `pharmacy_2023_2025`; filenames do not identify rows. Changed rows update without changing PK, unchanged rows are skipped, and absent rows are not deleted. Reconciliation checks selected source keys and complete mapped payloads. Any SQL error rolls back the entire load.

Catalog labels are normalized by trimming and treating empty/`-` as missing. Missing attributes retain known master values. Contradictory product attributes fail loading instead of choosing an arbitrary value. No unit conversions, amount formulas or inferred batch links are added.

Load receipts are generated under ignored `reports/oltp_ingestion/` (`load_<run_id>.json` and `load_summary.json`). They record files, row counts, inserts/updates/unchanged rows, warnings and reconciliation. A receipt-write failure after commit is reported separately; it cannot undo a committed transaction.

## Database and tests

```bash
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait db
docker compose -p inventory-dw-dss -f infra/docker-compose.yml exec db psql -U inventory -d inventory
# Stop while retaining data
docker compose -p inventory-dw-dss -f infra/docker-compose.yml stop db

uv run --group bootstrap python -m unittest discover -s tests/oltp_ingestion -p 'test_*.py' -v
uv run --group bootstrap python tests/oltp_ingestion/integration.py
```

Integration checks create and remove a uniquely named test database in the existing container. They validate schema idempotency and PK preservation, catalog integrity, repeated and changed upserts, source namespaces, dataset/date selection, partition overlap, batch FKs and rollback. They do not load fixtures into the operational database. Never use volume deletion as part of testing.

## SQL stages

- `sql/oltp/schema.sql`: complete idempotent schema, grouped into shared identities, sales, inventory and catalog enrichment. It creates a fresh database or brings an older schema forward without dropping existing data or identities.
- `sql/oltp/load.sql`: selected-key validation → shared catalog/header/batch resolution → sales upsert → inventory upsert → reconciliation and load receipt. Receipt SQL lives here alongside the statistics it reports.

Python coordinates the transaction, dynamic incoming column definitions and COPY streams. Static table definitions and load queries live in SQL. The loader executes these stages in one transaction under the existing advisory lock. `staging.schema_migration` retains old applied-version records and marks the one-time embedded catalog backfill; the loader no longer reads migration files or checksums. Do not execute load.sql independently: it requires the temporary incoming tables created by the loader.
