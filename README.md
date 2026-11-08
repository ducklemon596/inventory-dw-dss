# Pharmaceutical Inventory DW

Operational flow: **PostgreSQL OLTP → ClickHouse raw → dbt marts → DSS**. CSV loading is an optional way to initialize/update PostgreSQL from the supported pharmacy export. The DW extracts from the transactional database.

Read [architecture](docs/architecture.md), [source/data model](docs/data-model.md), [business semantics](docs/data-semantics.md) and [DSS handover](docs/dss-handover.md) for system meaning. Commands and implementation guidance live beside the owning code.

## Choose a destination

| Destination/task | Guide | Modes |
|---|---|---|
| Load PostgreSQL from the source export | [PostgreSQL loader](src/inventory_dw_dss/oltp_ingestion/README.md) | Full or inclusive date range; preparation is automatic |
| Load ClickHouse raw from PostgreSQL | [Raw loader](src/inventory_dw_dss/README.md) | Incremental by default, explicit full or inclusive date range |
| Build marts and run tests | [dbt transformations](transform/dbt/README.md) | All models, selected layer/model, or tests only |

## Start local services

Requires Python 3.12+, `uv`, Docker and Compose. From the repository root:

```bash
uv sync --locked
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait
```

[Services](infra/README.md) documents connection settings and persistent volumes. When PostgreSQL already contains the source tables, the routine pipeline is:

```bash
uv run --locked inventory-dw-dss load raw
uv run --locked inventory-dw-dss transform
```

Run these sequentially. Transform uses the governed UOM version pinned in the project configuration; the local guide explains selection and overrides. Read marts only after successful completion. Use `uv run --locked inventory-dw-dss --help` to inspect the public interface.

## Consumer boundary

The warehouse includes four conformed dimensions and three facts, with preserved sales lines, recorded inventory movements and observed daily balances. Sales have no verified warehouse assignment or completion/cancellation status. Unsupported conversion stays missing; missing days are not zero stock or demand. DSS forecasting and recommendations are not implemented. See [semantics](docs/data-semantics.md) before building consumer calculations.
