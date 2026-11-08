# Tests

| Folder | Scope |
|---|---|
| `extraction/` | Publication unit tests and disposable PostgreSQL/ClickHouse incremental regression |
| `staging/` | Compiled dbt normalization macros checked with read-only ClickHouse queries |
| `uom/` | Published-reference immutability and compiled-SQL safeguards in a disposable ClickHouse DB |
| `validation/` | Passport serialization, ordering and reconciliation failure cases without databases |
| `oltp_ingestion/` | Optional bootstrap parser/unit tests and disposable bootstrap integration |

```bash
uv run --locked python -m unittest discover -s tests/extraction -v
uv run --locked python -m unittest discover -s tests/validation -v
uv run --locked python -m unittest discover -s tests/uom -v
uv run --locked python tests/uom/integration.py
uv run --locked python tests/extraction/integration.py
uv run --locked python tests/staging/integration.py
uv run --locked --group bootstrap python -m unittest discover -s tests/oltp_ingestion -v
```

Integration tests require the running Compose servers. Extraction integration creates and
removes uniquely named test databases, including its own raw/DW schema; it never uses live
OLTP tables for mutations. Its dbt selection intentionally excludes historical-only tests.
Bootstrap integration is optional and documented with the bootstrap workflow.

SQL reconciliation and native dbt unit tests belong next to their analytical models or in
`transform/dbt/tests/`; run them with `dbt build` as shown in the main README. Do not add
Python copies of SQL business calculations to test them. Generated reports are ignored.
