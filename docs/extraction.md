# PostgreSQL → ClickHouse raw

Run from the repository root after starting the Compose databases:

```bash
uv sync --locked
uv run --locked inventory-dw-dss extract --batch-size 20000
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt build --select staging
```

Extraction reads only `oltp.*`. It does not import CSV/bootstrap modules or change
PostgreSQL data. Docker is used to host the servers; Python connects directly.

## Connection settings

| Environment variable | Default |
|---|---|
| `PGHOST` | `localhost` |
| `PGPORT` | `5433` |
| `PGDATABASE` | `inventory` |
| `PGUSER` | `inventory` |
| `PGPASSWORD` | `inventory_local` |
| `CLICKHOUSE_HOST` | `localhost` |
| `CLICKHOUSE_HTTP_PORT` | `8123` |
| `CLICKHOUSE_USER` | `dbt` |
| `CLICKHOUSE_PASSWORD` | `dbt_local` |
| `CLICKHOUSE_RAW_SCHEMA` | `raw` |

Compose publishes PostgreSQL on loopback. Set `POSTGRES_PORT` when launching
Compose to change its host port; set `PGPORT` accordingly for extraction.
`CLICKHOUSE_HTTP_PORT` is also used by Compose and the dbt profile.
Environment variables must be exported to the process; a `.env` file alone is
not automatically read by the Python CLI.

## Watermarks and raw representation

| Transaction table | Event time | PostgreSQL filter |
|---|---|---|
| `sales_line` | `sold_at` | `sold_at >= max(raw.sold_at)` |
| `inventory_movement` | `occurred_at` | `occurred_at >= max(raw.occurred_at)` |

Each transaction table has its own watermark, read directly from ClickHouse raw at
microsecond precision. If raw is absent or empty, all source records are selected.
The boundary is inclusive so new records sharing the latest timestamp are included.
The other 10 tables, including invoice/document headers, are refreshed completely
because they do not have event-time columns.

All PostgreSQL reads share one `REPEATABLE READ READ ONLY` transaction. A session
advisory lock serializes pipeline writers to the same raw destination. Named cursors
stream batches, keeping Python memory bounded.

Raw uses `MergeTree`, sorted by the source primary key. Each column stores canonical
PostgreSQL `::text` as `String` or `Nullable(String)`: dates use ISO format, NULL and
empty text stay distinct, and decimal digits do not pass through float. dbt staging
applies analytical types and business names. Staging identifiers use explicit entity
names such as `sales_invoice_id`, `product_batch_id` and `inventory_document_id`.
Quantities distinguish `sold_quantity`, `received_quantity`, `issued_quantity` and
`closing_stock_quantity`; percentages use `_percentage`, monetary adjustments use
`_amount`, and original composite descriptions use `_label`. Raw column names remain
unchanged. Dataset lineage is exposed as `dataset_name` and `dataset_row_number`. A source/raw
schema mismatch or duplicate raw primary key stops extraction for review.

Transaction deltas are loaded and checked in temporary tables. A replacement table
combines existing raw records whose PKs are absent from the delta with all delta
records. Counts and primary-key uniqueness must reconcile before publication. Reruns
replace matching PKs instead of appending duplicates. Empty deltas leave the existing
transaction table unchanged. PostgreSQL reads are incremental; ClickHouse still copies
existing raw rows locally when constructing a replacement.

This is event-time loading, not CDC: older late-arriving records, updates whose event
time is earlier than the watermark (including dates moved backwards), and transaction
deletions are not detected. Even deletions at the watermark leave existing raw records
in place. Reference/header refreshes do reflect updates and deletions; deleting a still
referenced record can therefore cause a dbt relationship test to fail and needs review.
There is no hidden lookback, separate watermark table or automatic historical reload.

## Publication and failure handling

New tables are loaded into a uniquely named `_extract_*` database. On success,
existing raw tables are atomically exchanged with the new tables; missing raw
tables are renamed into place. Old tables are removed only after all publications
succeed. Raw must use the `Atomic` database engine.

**The whole set of tables is not published atomically.** Run extraction and dbt
sequentially, and pause warehouse readers during publication if they require
cross-table snapshot consistency. The writer lock does not block dbt/readers.

A preparation/insert/validation error leaves the old raw tables intact. A caught
publication error reverses completed exchanges. A process crash, ambiguous network
failure during an exchange, or failed rollback requires inspecting `_extract_*`
and raw table names/UUIDs before retrying; do not blindly delete recovery tables.
The pipeline retains the work database after any publication exception, including
after reversing acknowledged exchanges, to allow inspection of ambiguous results.

`reports/raw_extraction.json` records status, source snapshot, each table's watermark,
selected/read rows, new PKs, reread PKs, raw counts before/after, key reconciliation,
column mappings and recovery/cleanup warnings. Reread PKs include both changed and
unchanged records; they are not a count of actual value changes. Each run replaces
this local report. The databases and their persistent volumes remain running.
