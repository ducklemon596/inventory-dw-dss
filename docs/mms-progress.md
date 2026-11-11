# MMS implementation ledger — plan: MMS_Logic_Evaluation_Implementation_Plan.md

## Scope and decisions

Implement P1–P5 in order. The plan is the available specification; its three
source documents and TN scripts/artifact are absent from this checkout.

- Ruling: Work in the user-selected checkout on `feature/add_model`; preserve
  existing files and the untracked plan. No merge, push or artifact fabrication.
- Ruling: The actual warehouse is ClickHouse, not DuckDB. Supply a read-only
  DuckDB adapter for a **normalized, explicitly verified MMS export**, not an
  unsafe rename of observed warehouse balances to available stock. Production
  export approval remains a dependency. Cost: one explicit handover/export step.
- Ruling: Ranking, coverage rounding and greedy partial allocation are provisional
  documented MVP policies until TN scripts arrive; no TN equivalence claim.
- Ruling: Use Python dataclasses and pytest; retain the existing src package layout.

## Pre-flight shared interfaces

| Producer → consumer | Contract / resolution |
| --- | --- |
| P1 → P2/P3 | Frozen, dated, versioned snapshot; sales history coverage explicit; no missing-as-zero inference |
| P2 → P3 | Exact MB2 feature names/order/version; missing artifact fails explicitly |
| P3 → P4/P5 | Immutable Review / Order results; allocated units distinct from suggestions |
| P1 → P4 | Outcome windows independent of feature snapshots; full daily observation required |
| P3 → P4 tracking | Persist configuration, complete result, model/data versions, and manager actions separately |

## Baseline

Initial system Python was 3.10, while the project requires 3.12. Installing uv
and using the available Python 3.12 environment. Before changes, existing suites
showed missing clickhouse dependency, Windows-only `fcntl` import failures, and
two immutable UOM byte-checksum failures. These are pre-existing; no reference
data or expected checksums will be changed to hide them.

## Execution

- P1: backend complete (8 data tests pass); production semantics approval pending.
- P2: backend complete (21 cumulative tests pass); real TN artifact validation pending.
- P3: backend complete (29 cumulative tests pass); provisional ranking/allocation policies documented.
- P4: backend complete (36 cumulative tests pass); TN result reproduction pending absent reference inputs.
- P5: standalone integration complete (43 cumulative tests pass, including
  Streamlit comparison/save/reopen/Q changes); integration into a separate team
  UI remains dependent on that UI becoming available.

## Acceptance status

| Plan capability | Implemented and verified | External acceptance still required |
| --- | --- | --- |
| P1 snapshots | In-memory + real DuckDB, strict 90-day coverage, dates/versions, quality checks | Approved pharmacy available-stock and historical-coverage export |
| P2 MB1–MB3/core | Catalog, validation, deterministic execution, real test-artifact loading | Original HistGB, exact preprocessing/environment/feature contract |
| P3 MB4 | Four profiles, pstar/K/tau/Q, partial allocation, Review/Order, diagnostics and comparison | TN5–TN7 policy/diagnostic equivalence |
| P4 evaluation/tracking | Independent windows, WAPE/Bias/ranking metrics, SOP exclusion, SQLite manager actions and follow-ups | TN numerical reproduction on original cohort/data/label definitions |
| P5 UI/demo | Service-backed Streamlit form, comparisons, saving/reopening, evaluation, explicit synthetic demo | Team UI/schema sign-off, screenshots/video/slides from approved data |

Build and dependency lock verification passed (`uv build`, `uv lock --check`).
The full existing test suite cannot collect on Windows because its bootstrap
uses POSIX `fcntl`. Excluding that test directory gives four pre-existing
failures: two UOM byte checksums, the bootstrap dispatch import and a test's
hardcoded POSIX dbt path. No existing source/tests/reference bytes were changed.
Database-backed dbt/integration acceptance was not run: this change neither
modifies warehouse models nor has a running approved production export.

## Final independent review

The independent reviewer found no Critical issues and three Important issues.
All three were reproduced by failing regressions and fixed:

- Artifact temporal eligibility: require a supervised-data cutoff covering
  training/tuning/calibration labels; enforce at each historical T and save it
  in execution metadata. Verified at wrapper and backtester boundaries.
- Manager widget state: reset actions, edits and notes on a successful new run;
  an old edited quantity cannot silently move to a changed Q/tau plan.
- Database errors: normalize missing DuckDB snapshot/outcome tables and files to
  service validation errors; show native SQLite/DuckDB errors through the UI.

Additional important quality fix: negative balances are counted separately from
existing zero-stock labels, verified by a failing-then-passing regression.

Final: minor (deferred): Scenario summary/metadata dictionaries are shallowly
mutable; callers should treat them as read-only. Snapshot rows and Review/Order
items are immutable. Defensive deep-freezing of result maps is deferred.
The review's other minor (stale P5 ledger status) was already corrected during
the review; current status above is authoritative.

Rulings on the review's declined-to-judge list: original TN equivalence,
production stock/export semantics and calibration evidence remain externally
unverified, as documented above; cost if wrong is invalid production decisions,
so this is explicitly an integration MVP until those inputs are approved.
Global optimality/purchasing optimization and causal benefit claims remain
outside scope; greedy allocation and observational metrics are labelled as such.
Existing Windows/UOM failures remain separate; no claim that the full warehouse
suite passed. The UOM checksum issue was traced to Git checkout CRLF conversion:
LF-normalized hashes match the unchanged published expectations exactly.

## Final verification

- `py -3.12 -m uv run --locked --extra ui --group dev pytest tests/mms -q`:
  **49 passed**, including both data adapters, artifact inference/cutoff, model
  execution, K/Q invariants, comparisons, backtests, tracking and UI regressions.
- `.venv/Scripts/python.exe -m pytest tests/mms tests/extraction -q`:
  **53 passed, 4 subtests passed**. Existing extraction behavior remains green.
- `py -3.12 -m uv build`: source distribution and wheel built; MMS/UI included.
- `py -3.12 -m uv lock --check`, `git diff --check`, MMS compileall: passed.
- Full-repository pytest attempted: blocked during collection by existing Windows
  `fcntl` import; separately inspected existing CLI/UOM failures described above.

Changes remain in the requested checkout on `feature/add_model`, without commit,
merge or push. No warehouse rebuild, source reload or production write occurred.
Remaining external acceptance items are listed in the table above; they are not
silently counted as completed work.
