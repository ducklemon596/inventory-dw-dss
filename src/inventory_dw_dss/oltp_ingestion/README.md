# Optional OLTP initialization

This package reconstructs PostgreSQL from the supplied CSVs. It is outside normal DW operation and requires `uv --group bootstrap` for pandas.

| File | Responsibility |
|---|---|
| [cli.py](cli.py) | `bootstrap prepare` / `bootstrap load`, interval/dataset/date options |
| [preprocessing.py](preprocessing.py) | Chunked parsing, preservation of raw/source keys, deterministic time partitions and checksum manifest |
| [loading.py](loading.py) | Validate selected partitions, stream COPY, execute schema/upsert SQL in one transaction, write receipt |

This README is the operating guide for this isolated workflow. For schema/loading responsibilities, see [SQL stages](../../../sql/oltp/README.md) for schema/loading responsibilities. Keep source codes as strings, preserve RowNumber, and do not introduce inferred UOM factors or financial formulas here.

Tests cover parser boundaries and disposable-database upserts; use [bootstrap tests](../../../tests/oltp_ingestion/README.md). Do not initialize or reload the operational database as a test fixture.
