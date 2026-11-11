# MMS production integration

The user authorized finishing all four follow-up areas: ClickHouse connectivity,
original HistGB integration, TN regression verification and team UI integration.
Continue in the existing feature branch; preserve warehouse semantics and do not
claim that new models or results are the absent original TN artifacts.

**Scope update:** The user explicitly authorized creating new artifacts and
experiments because the originals do not exist. Add reproducible training from
normalized snapshots with independent future labels, and a fully synthetic
trained bundle for end-to-end validation. Identify it as new work, never original
TN reproduction. Source CSVs have since been downloaded and verified, but they
do not establish pharmacy-wide available stock: at 2025-06-30 no SKU has exact-day
observations at both locations. Keep real source evidence separate from simulation.

## Approach

Use a read-only ClickHouse provider against approved **normalized MMS tables**,
with an immutable release metadata gate. A raw-mart audit explains why the
existing observed marts cannot prove available stock or absent-day zero sales.
This extends the existing DuckDB contract, rather than introducing unverifiable
carry-forward or automatic zero filling. A direct raw-mart-to-available-stock
mapping was rejected because it would contradict the warehouse documentation.
An ETL rebuild on every UI request was rejected because scenarios must only read.

Use the original trusted HistGB loader unchanged in principle, add an artifact
check command and a machine-readable reference-suite runner. Reference cases
must be provided by the experimental owner, and identify versions and expected
outputs; absent cases are reported as unavailable, never reproduced by a new model.

One runtime factory supplies demo, DuckDB or ClickHouse services and outcomes to
both the standalone Streamlit page and an embedding team application. Existing
environment variables remain compatible; explicit production modes never fall
back to the synthetic demo.

## Boundaries and evidence

Only SELECT queries reach ClickHouse. Identifiers are validated; values are bound
parameters. Metadata approves pharmacy scope, available-stock definition, daily
sales coverage and SOP rules, and pins immutable release/data versions. Read
metadata before and after a snapshot/outcome load to reject release changes.
Published releases must themselves be immutable; read checks cannot certify an
owner who mutates rows without changing the release ID.

CLI commands return strict JSON and nonzero status for failed readiness or
reference checks. Reports identify missing external files and unavailable live
services. Tests use actual DuckDB/sklearn/SQLite/Streamlit where available and
explicit fake ClickHouse clients to verify query boundaries; live acceptance is
separate and cannot be claimed without a server and approved data.
