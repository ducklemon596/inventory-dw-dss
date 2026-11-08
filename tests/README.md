# Testing and acceptance

Run from the repository root with the [services](../infra/README.md) running. Build dbt before tests that inspect its compiled SQL. Pin the same UOM version in builds/tests/analyses. Compilation proves SQL rendering, not correct data.

## What each layer protects

| Test group | Protects / why it matters | On failure |
|---|---|---|
| [Source and Staging](../transform/dbt/tests/staging/README.md) | Parse strictness, source row counts, source keys, batch/product association | Trace the failing PK into raw; distinguish missing source values from invalid format |
| [Intermediate](../transform/dbt/tests/intermediate/README.md) | Grain, row preservation, recorded balance, predecessor/segment correctness | Inspect the exact ledger/product scope; do not repair balances or change ordering to hide a gap |
| [UOM](../transform/dbt/tests/uom/README.md) | Version/approval, exact arithmetic, compatible stock evidence and coverage | Check immutable reference, version literal and unit evidence; never promote a candidate |
| [Marts](../transform/dbt/tests/marts/README.md) | Fact/Dimension grains, exact schemas, FK validity, JOIN cardinality, observation/measure reconciliation | Inspect duplicate/missing parent keys, projection drift or NULL replacement |
| [Generic tests](../transform/dbt/tests/generic/README.md) | Reusable uniqueness, complete source preservation and schema/JOIN checks | Read returned failing keys; each generic test is configured in model YAML |
| [Public CLI](cli/README.md) | Scope/date validation, optional dependencies, destination dispatch and dbt selection/failure status | Check command arguments before destination execution |
| [Python publication](extraction/README.md) | Extractor failure/lock/retry boundary in disposable databases | Inspect its temporary test logs and recovery scope, not production data |
| [Python reference](uom/README.md) | Immutable byte checksums and exact seed union; compiled UOM failure fixtures | Restore altered references or fix version publication, not expected checksum values |
| [Python mart regression](marts/README.md) | Proves compiled tests reject orphan/fan-out/NULL/schema faults | Ensure the pinned full build produced compiled contracts first |
| [Optional bootstrap](oltp_ingestion/README.md) | CSV parsers, deterministic partitions and transactional upsert/rollback | Reproduce only in the disposable database; do not reload operational OLTP |

Not-null, uniqueness, relationships, source-preservation and JOIN-cardinality checks are distinct. A LEFT JOIN can preserve an orphan while an FK test rejects it; a duplicate parent can multiply rows while an orphan check passes. Full acceptance needs all of them.

## dbt commands

```bash
# Complete acceptance: models, seed, data tests and native unit fixtures.
uv run --locked inventory-dw-dss transform
# Build sales ancestors and required Dimensions.
uv run --locked inventory-dw-dss transform --select +fct_sales_line dim_product dim_unit dim_date
# Test existing selected outputs without rebuilding them.
uv run --locked inventory-dw-dss transform --test --select fct_sales_line
```

`dbt build` can gate downstream nodes on tests; already published tables are not rolled back by a later failure. Run the full build for acceptance after targeted development. Read `transform/dbt/target/run_results.json` for status/failing nodes, `target/compiled/inventory_dw/` for rendered SQL and `logs/dbt.log` for executed queries/errors. A singular test returns failing rows; a zero-row result passes. Do not change source counts or remove tests to make an unexpected export pass.

## Python suite

```bash
uv run --locked --group bootstrap python -m unittest discover -s tests/cli -v
uv run --locked python -m unittest discover -s tests/extraction -v
uv run --locked python -m unittest discover -s tests/uom -v
uv run --locked --group bootstrap python -m unittest discover -s tests/oltp_ingestion -v
uv run --locked python tests/staging/integration.py
uv run --locked python tests/uom/integration.py
uv run --locked python tests/marts/integration.py
uv run --locked python tests/extraction/integration.py
uv run --locked --group bootstrap python tests/oltp_ingestion/integration.py
```

Unit tests require no running databases. Staging integration compiles a temporary fixture from the real macros, then evaluates its cases with SELECTs; dbt connection probes may create/drop temporary probe tables. Other integration scripts create uniquely named disposable databases, inject their own fixtures and clean them up. Extraction integration runs its own staging dbt selection in a temporary project; it does not extract into production raw. Bootstrap integration starts existing services if needed but loads only its disposable database. Do not run production `load postgres` or `load raw` as a substitute for these isolated fixtures.
