# Load PostgreSQL from the supported CSV export

This optional initialization path reads `data/raw/sales_raw.csv` and `data/raw/stock_raw.csv` and upserts the local Compose PostgreSQL database (`inventory`, user `inventory`, service `db`). It is separate from normal DW extraction. Both source files and a running Docker daemon are required; pandas is installed through the optional `bootstrap` group.

Run from the repository root. The loader starts the existing Compose services if needed and uses the container's PostgreSQL client.

## Full load

```bash
uv run --locked --group bootstrap inventory-dw-dss load postgres --full
```

This reads all sales and stock rows in the supported export. It creates the complete schema if absent and inserts or updates transactions by `(source_dataset, source_row_number)`. It preserves existing PKs, skips identical rows and retains rows absent from the source. Full load does not truncate tables.

## Time-range load

```bash
uv run --locked --group bootstrap inventory-dw-dss load postgres --start 2023-01-01 --end 2023-01-31
```

Both endpoints are required, inclusive calendar dates in `YYYY-MM-DD`. Selection uses each row's event date, including when a range cuts through a monthly partition. Add `--dataset sales` or `--dataset stock` when loading only one transaction dataset; the default is `both`. A range matching no rows fails before opening the database load transaction.

`--full` and dates cannot be combined. Inspect the interface with:

```bash
uv run --locked inventory-dw-dss load postgres --help
```

## Automatic preparation and receipts

`load_source()` checks the original-file hashes and the prepared schema/version. When the monthly cache is missing or the original export changed, it calls the existing pandas preparation automatically. Source codes and RowNumber remain intact; raw columns and parsed composites are retained. Defaults are monthly partitions and 100,000-row preparation chunks. Normal operation needs no separate prepare command.

Cached partitions are validated before COPY. A corrupt or edited cache fails safely; remove the generated `data/processed/1mo` directory and rerun the same load to regenerate it. Preparation publishes a complete checksummed set atomically and retains the preceding complete set if it fails.

The PostgreSQL load uses one transaction and an advisory lock. Catalogs, headers and batches resolve before detail upserts; reconciliation verifies the selected source keys and mapped values. Any SQL failure rolls back the whole load. Contradictory known product attributes fail rather than choosing an arbitrary classification. No new quantity conversion, batch link or financial formula is inferred here.

Receipts are written to `reports/oltp_ingestion/load_<run_id>.json` and `load_summary.json`, including selected files/date range, read/insert/update/unchanged counts, warnings and reconciliation. A receipt-write error after commit is reported explicitly; it cannot undo committed data.

## Code and maintenance

| Module | Responsibility |
|---|---|
| [preprocessing.py](preprocessing.py) | Parse composites, retain source fields, publish deterministic partitions and manifest |
| [loading.py](loading.py) | Automatic preparation, selected-file validation, COPY and transactional schema/upsert orchestration |
| [Project CLI](../cli.py) | Public destination/date/dataset arguments and input validation |
| [SQL stages](../../../sql/oltp/README.md) | Complete schema, catalog resolution, upserts and reconciliation |

The internal preparation API also supports `1d`, `3d` and `1w` for parser/partition regression; the public load command uses the monthly default. [Bootstrap tests](../../../tests/oltp_ingestion/README.md) run full/range/repeat/update/rollback scenarios in disposable databases. Connection variables documented for extraction do not redirect this Compose-based CSV loader to another PostgreSQL database.
