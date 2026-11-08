# Datasets

- `raw/sales_raw.csv`: 649,656 source sales rows, 35 columns.
- `raw/stock_raw.csv`: 804,027 source stock rows, 15 columns.
- `processed/<interval>/`: generated sales/stock partitions and checksum manifest, ignored by Git.

Raw data is preserved unchanged. Codes and RowNumber must remain stable for idempotent loading. Preparation preserves raw columns and adds parsed fields; it does not rewrite the inputs. Prepared datasets can be reproduced with:

```bash
uv run --group bootstrap inventory-dw-dss bootstrap prepare --interval 1mo
```

The loader supports `1d`, `3d`, `1w` and `1mo`, dataset selection and inclusive date ranges. See [ingestion instructions](../src/inventory_dw_dss/oltp_ingestion/README.md) and [source data dictionary](../docs/source-system.md).

CSV files are upstream ingestion inputs, not operational DW sources. Once OLTP is populated, DW extraction reads PostgreSQL without a runtime dependency on this directory. Generated load receipts live in `reports/oltp_ingestion/`, outside the datasets.

`reference/` contains the export passport, immutable pair-level UOM decisions and earlier coverage-only evidence. These serve different roles: the pair-level approved decisions form the governed dbt seed; the coverage-only summary cannot authorize a conversion. None is an extraction input. See [reference provenance](reference/README.md). Validators read original/prepared files as evidence and do not regenerate them.
