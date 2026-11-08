# Local database services

[docker-compose.yml](docker-compose.yml) runs PostgreSQL 17 and ClickHouse 26.10.3.7. Python, `uv` and dbt run on the host; neither database container runs the transformation pipeline.

```bash
docker compose -p inventory-dw-dss -f infra/docker-compose.yml up -d --wait
docker compose -p inventory-dw-dss -f infra/docker-compose.yml ps
docker compose -p inventory-dw-dss -f infra/docker-compose.yml logs --tail 100 clickhouse
# Stop without deleting stored data:
docker compose -p inventory-dw-dss -f infra/docker-compose.yml stop
```

Use the project name `inventory-dw-dss` consistently: named volumes hold the existing databases. Do not use volume removal as a reset or test command.

## Connections

| Client setting | Default | Responsibility |
|---|---|---|
| `PGHOST`, `PGPORT` | `localhost`, `5433` | Host-side raw loading connects here |
| `PGDATABASE`, `PGUSER`, `PGPASSWORD` | `inventory`, `inventory`, `inventory_local` | PostgreSQL source; Compose sets these server values directly |
| `POSTGRES_PORT` | `5433` | Compose host port; export matching `PGPORT` if changed |
| `CLICKHOUSE_HOST`, `CLICKHOUSE_HTTP_PORT` | `localhost`, `8123` | Host Python/dbt HTTP connection |
| `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` | `dbt`, `dbt_local` | Compose, Python and dbt credentials |
| `CLICKHOUSE_RAW_SCHEMA` | `raw` | Extraction destination and dbt source schema |
| `CLICKHOUSE_DB` | `inventory_dw` | dbt destination database |

Export environment variables before running host commands; Python does not automatically load `.env`. Compose uses its own environment interpolation. The dbt [profile](../transform/dbt/profiles.yml) defines `secure: false`, `verify: false` for local HTTP; use appropriate TLS settings when configuring a remote HTTPS service. Local credentials and exposed ports are development defaults, not a production deployment policy.

## Inspect data

```bash
docker compose -p inventory-dw-dss -f infra/docker-compose.yml exec -T db psql -U inventory -d inventory -c 'SELECT count(*) FROM oltp.sales_line'
docker compose -p inventory-dw-dss -f infra/docker-compose.yml exec -T clickhouse clickhouse-client --user dbt --password dbt_local --query 'SHOW TABLES FROM inventory_dw'
```

OLTP initialization is explicit: [PostgreSQL load](../src/inventory_dw_dss/oltp_ingestion/README.md). ClickHouse raw is published by [extraction](../src/inventory_dw_dss/README.md); dbt creates the analytical relations. Health checks verify server readiness, not source completeness or analytical correctness.
