# Inventory DW & DSS

The transactional PostgreSQL database is the official Data Warehouse source:

`PostgreSQL (OLTP) → Extraction → DuckDB → dbt → Data Marts → DSS (Streamlit)`

This repository currently implements CSV preparation, time partitioning and incremental OLTP ingestion. Extraction, DuckDB, dbt, data marts and Streamlit are not implemented yet. CSV ingestion is an upstream workflow, separate from operational DW execution.

## Structure

```text
data/                       raw inputs and prepared partitions
  raw/
  processed/                generated, ignored by Git
src/inventory_dw_dss/
  cli.py                    project CLI
  oltp_ingestion/            upstream preparation and loading
sql/oltp/                   complete schema and load SQL, grouped by stage
tests/oltp_ingestion/        unit tests, integration checks and fixtures
infra/                      PostgreSQL Docker Compose configuration
docs/
  architecture.md
  oltp/                     schema, data dictionary, ingestion guide and ERD
```

## Setup and commands

Requires Python 3.12+, uv, and Docker Compose for database loading.

```bash
uv sync --locked
uv run inventory-dw-dss --help

# Optional upstream ingestion dependencies
uv sync --locked --group bootstrap
uv run --group bootstrap inventory-dw-dss bootstrap --help

# Prepare raw CSVs; default interval is one calendar month
uv run --group bootstrap inventory-dw-dss bootstrap prepare --interval 1mo

# Load all prepared data, or select a dataset/date range
uv run --group bootstrap inventory-dw-dss bootstrap load --interval 1mo --all
uv run --group bootstrap inventory-dw-dss bootstrap load --interval 1mo \
  --from 2023-01-01 --to 2023-01-31 --dataset sales
```

Skip ingestion when OLTP is already populated. There is no operational DW command yet. The `bootstrap` CLI and dependency group retain their existing names; their implementation lives in the application package.

## Validation

```bash
uv run --group bootstrap python -m unittest discover -s tests/oltp_ingestion -p 'test_*.py' -v
# Uses fixtures and a disposable test database; never loads the operational database
uv run --group bootstrap python tests/oltp_ingestion/integration.py
```

See [architecture](docs/architecture.md), [OLTP schema and ERD](docs/oltp/schema.md), [data dictionary](docs/oltp/data-dictionary.md), [ingestion workflow](docs/oltp/ingestion.md), and [dataset organization](data/README.md).
