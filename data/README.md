# Datasets

- `raw/sales_raw.csv`: 649,656 source sales rows, 35 columns.
- `raw/stock_raw.csv`: 804,027 source stock rows, 15 columns.
- `processed/<interval>/`: generated sales/stock partitions and checksum manifest, ignored by Git.

Raw files are preserved unchanged. The [PostgreSQL command](../src/inventory_dw_dss/oltp_ingestion/README.md) automatically prepares monthly partitions when needed, preserving source codes, RowNumber and all raw columns. Choose full load or inclusive event dates through that command; operational users do not run preparation separately.

CSV files are upstream ingestion inputs, not operational DW sources. Once OLTP is populated, DW extraction reads PostgreSQL without a runtime dependency on this directory. Generated load receipts live in `reports/oltp_ingestion/`, outside the datasets.

`reference/` contains immutable pair-level UOM decisions used by the governed dbt seed, an earlier coverage-only summary that cannot authorize conversions, and an archived export passport retained as research provenance. Only the governed mapping snapshots feed transformations; the passport is not a runtime input. See [reference provenance](reference/README.md).
