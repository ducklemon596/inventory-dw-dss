# Original POS export

`sales_raw.csv` and `stock_raw.csv` are unchanged source evidence. [The data dictionary](../../docs/source-system.md) explains fields and samples. Keep codes and RowNumber intact; do not edit these files to repair analytical output.

Only [optional OLTP preparation](../../src/inventory_dw_dss/oltp_ingestion/README.md) reads these CSVs for loading. Normal extraction reads PostgreSQL. Read-only [source validation](../../scripts/README.md) also reads the originals to prove lineage for the verified export. Reference fingerprints are under [data/reference](../reference/README.md).
