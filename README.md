# Pharmaceutical Inventory DW

This repository builds analytical sales and inventory tables for DSS consumers. The operational path is **PostgreSQL OLTP → Python extraction → ClickHouse raw → dbt → Data Marts**. Original CSVs are used only by optional OLTP bootstrap and retained source evidence; extraction reads PostgreSQL.

Start with [system architecture](docs/architecture.md), [data model](docs/data-model.md), [data semantics](docs/data-semantics.md), and the [DSS handover](docs/dss-handover.md). Implementation guides live beside code: [Python pipeline](src/inventory_dw_dss/README.md), [dbt project](transform/dbt/README.md), [database services](infra/README.md), [OLTP SQL](sql/oltp/README.md), and [tests](tests/README.md).

## Run the operational pipeline

Requirements and environment configuration are in [infra/README.md](infra/README.md). Start services and install the locked dependencies:

```bash
uv sync --locked
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait
```

Extract from PostgreSQL, then build dbt models with an explicitly selected immutable UOM mapping version:

```bash
uv run --locked inventory-dw-dss extract --batch-size 20000
uv run --locked dbt build --project-dir transform/dbt --profiles-dir transform/dbt \
  --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

Run the stages sequentially. Publish results to DSS readers only after extraction and the complete dbt build succeed. Detailed selection, failure handling and validation instructions are in the local [Python](src/inventory_dw_dss/README.md) and [dbt](transform/dbt/README.md) guides.

## Optional OLTP initialization

Only when reconstructing an empty PostgreSQL database from the supplied source export, use the isolated [bootstrap workflow](src/inventory_dw_dss/oltp_ingestion/README.md). It is not part of normal DW execution. Do not reload a populated operational database to run tests.

## Current system boundaries

The warehouse includes 12 Staging views, seven Intermediate/diagnostic views, two Intermediate tables, four dimensions and three facts. Sales represent recorded lines, not verified net demand, and have no warehouse assignment. Converted quantities remain NULL when unsupported. Inventory facts preserve recorded movements and balances; they do not certify physical or available stock, fill missing days or repair discontinuities. See [data semantics](docs/data-semantics.md) and [source evidence](docs/source-system.md).
