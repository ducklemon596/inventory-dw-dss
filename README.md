# Inventory DW & DSS

Pharmaceutical sales and inventory data for analysis and decision support.

`PostgreSQL OLTP → Python extraction → ClickHouse raw → dbt staging → Data Marts → DSS`

Extraction and 12 staging views are implemented. Dimensional models, marts and DSS
are not implemented yet. PostgreSQL is the operational data source.

## Run the pipeline

Requires Python 3.12+, uv and Docker Compose. Run from the repository root:

```bash
uv sync --locked
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait
uv run --locked inventory-dw-dss extract --batch-size 20000
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt build --select staging
```

Extraction reads sales since `max(raw.sales_line.sold_at)` and movements since
`max(raw.inventory_movement.occurred_at)`, including records equal to each watermark.
It merges by primary key and refreshes the other 10 tables completely. An absent or
empty transaction table is loaded in full. No source CSVs are read by this workflow.

Run extraction and dbt sequentially: raw publication is atomic per table, not across
all tables. Transactions arriving or changing earlier than the watermark, and deleted
transactions, are not synchronized automatically. See [extraction](docs/extraction.md)
for connection settings, mappings, limitations and recovery.

Both databases keep data in named Docker volumes. Local endpoints are PostgreSQL
`localhost:5433` and ClickHouse HTTP `localhost:8123`. Preserve the Compose project
name `inventory-dw-dss` to reuse existing volumes.

## Project layout

```text
src/inventory_dw_dss/       CLI, extraction and optional OLTP bootstrap
transform/dbt/              sources, staging views and data quality tests
infra/                     PostgreSQL and ClickHouse Compose services
sql/oltp/                  OLTP schema and bootstrap load SQL
tests/extraction/          incremental and failure-recovery tests
tests/oltp_ingestion/      optional bootstrap tests and fixtures
docs/                      architecture, extraction and OLTP reference
```

CSV bootstrap is optional and only needed to reconstruct OLTP. Its dependencies
are isolated in the `bootstrap` group. Follow [bootstrap instructions](docs/oltp/ingestion.md);
skip bootstrap when PostgreSQL already contains the operational data.

## Validate

```bash
uv run --locked python -m unittest discover -s tests/extraction -v
# Uses disposable databases on the running servers; includes an actual dbt build.
uv run --locked python tests/extraction/integration.py
uv run --locked python tests/staging/integration.py

DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt debug
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt parse
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt compile --select staging
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt build --select staging
```

The active extraction report is `reports/raw_extraction.json`. dbt writes its test
results to `transform/dbt/target/run_results.json`. Integration tests clean up their
own databases and leave the containers running.

[Architecture](docs/architecture.md) · [OLTP schema](docs/oltp/schema.md) ·
[Data dictionary](docs/oltp/data-dictionary.md) · [Staging rules](docs/staging.md)
