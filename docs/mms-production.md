# MMS connection, training and verification

## Real source download

The README's Mendeley v2 archive was downloaded and its nested source ZIP read
without executing its scripts. Only the two original raw CSVs were extracted.

| File | Rows | Bytes | SHA256 |
| --- | --- | --- | --- |
| data/raw/sales_raw.csv | 649656 | 151329337 | d306bfdadfdf2e3ea5cd1eeb687c2fb827579407d0c2a85d550b433ae1239ec9 |
| data/raw/stock_raw.csv | 804027 | 142451516 | a0da6a0295e32f3ad2dae67bec706ad2c290181c35bf2aaf1eecd375199174fd |

CRC was checked while streaming ZIP members, byte counts matched the directory,
and every RowNumber is consecutive from 1 to the row count. Headers/contents were
preserved. Archives, receipts, source files, model binaries and generated reports
are local ignored artifacts, not additions to Git.

Audit the real data without changing warehouse semantics:

```powershell
uv run --locked --extra mms inventory-mms audit-source --date 2025-06-30
```

The downloaded export spans 2023-01-02–2025-12-31. Sales contain 3,149 SKUs;
stock contains 4,366, with Apotek and Gudang Obat 1. At 2025-06-30, only one
SKU has 90 consecutive observed sales days in one recorded unit, no SKU has
exact-day observations at both stock locations, and no SKU has all 30 subsequent
days observed at both locations. This does **not** imply that all other stock
was zero. It demonstrates why these CSVs cannot be automatically passed off as
the strict pharmacy-total availability contract. Audit output is diagnostic;
source sequence completeness does not establish availability or arrival times.

## Fully trained simulation bundle

The user authorized creating new artifacts because the original TN code/model
is unavailable. This is a separately labelled simulation, not invented original
results or a trained model claimed to use the downloaded pharmacy records.

```powershell
uv run --locked --extra ui inventory-mms bootstrap-demo --output reports/mms-trained-demo --seed 7
uv run --locked --extra ui streamlit run reports/mms-trained-demo/app.py
```

The command creates an immutable directory with:

- `data.duckdb`: deterministic simulated daily sales, stock and independent outcomes.
- `artifact/histgb.joblib`, `artifact/manifest.json`: an actually trained HistGB,
  ordered features, checksum, exact sklearn version and training fingerprint.
- `new-experiments.json`: NEW1–NEW7 demand/risk, coverage, profile comparison,
  constraints, diagnostics and decision tracking demonstrations.
- `reference.json`: a baseline captured from this implementation for future
  regression checks, **not independent confirmation of correctness or TN equivalence**.
- `decisions.sqlite`, `app.py`: a saved example and a runnable team-embedding example.

Training dates are weekly 2025-04-01 through 2025-05-27; seven-day labels end on
2025-06-03. Evaluation dates 2025-06-30, 2025-07-14 and 2025-08-15 follow that
cutoff. No tuning or calibration uses those dates. SOP-affected windows are
excluded. HistGB has a fixed seed and fixed parameters; risk scores are not
asserted to be calibrated probabilities. Reusing an existing output path fails
rather than overwriting a prior bundle. To regenerate, use a new version path.

The old four-SKU fixed-score fixture remains available for fast tests. The new
trained simulation UI always displays a synthetic-data warning, even though its
source is a DuckDB file. Neither mode is production readiness evidence.

## ClickHouse setup and runtime

The existing marts remain unchanged. The data owner can use
[normalized_release.sql](../sql/mms/normalized_release.sql) to publish separate
MMS tables. Populate a new immutable release completely before publishing exactly
one metadata row for that release. The row must name `mms-v1`, `pharmacy_total`,
the approved data version, approver and approval reference. All four verification
flags must explicitly be true: available stock, daily sales coverage, units,
and SOP rules. Never set flags merely to silence an error.

Metadata is read before and after snapshot/outcome reads. Release changes,
missing/duplicate metadata, invalid flags, mixed data versions and malformed
rows fail. Release IDs are bound values; database identifiers are validated.
Readers cannot detect an owner changing rows without changing the immutable
release ID; immutability is also a publication contract. Use a SELECT-only account.
The application performs only SELECT, with no ETL, DDL or server writes.

```powershell
$env:MMS_DATA_SOURCE = 'clickhouse'
$env:MMS_RELEASE_ID = 'approved-release-v1'
$env:CLICKHOUSE_DB = 'inventory_dw'
$env:CLICKHOUSE_HOST = 'localhost'
$env:CLICKHOUSE_HTTP_PORT = '8123'
# Set CLICKHOUSE_USER / CLICKHOUSE_PASSWORD to your read-only credentials.
$env:MMS_ARTIFACT_PATH = 'C:/approved/histgb.joblib'
$env:MMS_MANIFEST_PATH = 'C:/approved/manifest.json'
uv run --locked --extra mms inventory-mms audit-warehouse
uv run --locked --extra mms inventory-mms readiness --date 2025-06-30
uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/ui.py
```

`CLICKHOUSE_SECURE=true` enables TLS. Existing `MMS_DUCKDB_PATH` configuration
remains supported. Partial production settings fail; they never silently choose
the fixed-score demo. Clients are short-lived and do not share HTTP sessions.
Readiness checks are limited operational checks, not owner approval or evidence
that a policy improves costs/stockouts. The raw warehouse audit always reports
semantic approval blockers rather than certifying observed balances.

## Train a new model on approved normalized data

This command requires snapshots and independent observed outcomes, but does not
require a pre-existing artifact. For ClickHouse, normal release approval applies.

```powershell
uv run --locked --extra mms inventory-mms train-histgb --dates 2025-04-01,2025-04-08,2025-04-15 --output reports/model-new-v1 --artifact-version model-new-v1 --data-kind verified --horizon 7 --seed 7
uv run --locked --extra mms inventory-mms check-artifact --artifact reports/model-new-v1/histgb.joblib --manifest reports/model-new-v1/manifest.json
```

`verified` is an explicit operator declaration backed by source approval, not an
automatic inference from a file name. Declared synthetic dataset versions cannot
be trained as verified data. Training requires at least 20 eligible incident-risk
samples and both labels. Existing zero/negative stock is excluded; a missing
outcome window fails, and SOP-affected dates are listed as excluded. Features
are available stock, sales 7d/30d and MA90 velocity; the new protocol is documented
in the manifest. Original TN feature compatibility is not claimed.

## Reference suite and team UI

`inventory-mms verify-reference --reference path/to/reference.json` checks a
supplied reference suite. It refuses missing original files rather than calling
new results a reproduction. Every case specifies cohort, artifact/data versions,
date-specific snapshot versions, expected output paths and (for backtests) outcome
version, decision dates and horizon. Unknown paths, empty suites, version/cohort
mismatches and non-finite JSON are errors. Differences yield a failed report.
Exit codes: 0 success, 1 failed check/reference, 2 unavailable/invalid inputs;
argument syntax errors use standard argparse behavior.

The generated `reference.json` is a complete executable example of this schema.
Call `run_reference_suite(service, spec, outcomes)` from Python to use an injected
source without setting environment variables. Its frozen snapshots prevent a
second read from drifting between version validation and evaluation.

To embed in a team Streamlit app:

```python
from inventory_dw_dss.mms.runtime import build_runtime
from inventory_dw_dss.mms.ui import render

# The host app owns st.set_page_config and can cache its runtime.
render(configure_page=False, application_runtime=build_runtime())
```

If no team application is supplied, the standalone page and generated app are
the concrete integration targets. Integration into an unknown external repo
cannot be claimed. Saved sessions and their manager-entered actions remain
separate from inferred transaction follow-ups.
