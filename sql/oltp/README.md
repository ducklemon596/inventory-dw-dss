# OLTP schema and loading SQL

| File | Execution stage |
|---|---|
| [schema.sql](schema.sql) | Complete idempotent OLTP/staging definitions, compatibility additions and guarded catalog backfill |
| [load.sql](load.sql) | Incoming validation → catalog/header/batch resolution → detail upserts → selected-key/payload reconciliation and receipt |

The [Python loader](../../src/inventory_dw_dss/oltp_ingestion/README.md) opens one transaction, takes an advisory lock, applies schema SQL and creates temporary incoming tables before COPY and load SQL. Do not execute `load.sql` alone. Identity PKs remain stable when matching `(source_dataset,source_row_number)` rows are updated; absent rows are not deleted.

The retained migration metadata supports an embedded one-time backfill; there are no separate migration files to run. Do not remove guards or replay backfills without testing existing data. [OLTP model](../../docs/data-model.md), [data dictionary](../../docs/source-system.md) and [bootstrap operations](../../src/inventory_dw_dss/oltp_ingestion/README.md) explain source meanings. Schema/upsert regression uses a disposable database, not the operational source.
