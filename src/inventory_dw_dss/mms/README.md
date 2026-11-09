# Model Management Subsystem

MMS implements MA90, HistGB inference, coverage suggestions, scenario allocation,
historical metrics and SQLite decision tracking behind `MMSService`. Production
requires a verified normalized export and the original trusted trained bundle;
the included demo is wholly synthetic. No scenario action triggers ETL or dbt.

From the repository root (Python 3.12):

```powershell
uv sync --locked --extra ui --group dev
uv run --locked --extra mms python -m inventory_dw_dss.mms.demo
uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/ui.py
uv run --locked --extra ui --group dev pytest tests/mms -q
```

If uv is not on PATH on Windows, use `py -3.12 -m uv` in its place.

```python
from inventory_dw_dss.mms.core.schemas import ScenarioConfig, to_dict
from inventory_dw_dss.mms.demo import build_demo_service

service = build_demo_service()  # visibly synthetic; never use as a production fallback
config = ScenarioConfig("2025-06-30", profile="RiskFirst", pstar=0.3,
                        top_k=50, unit_budget_q=15, coverage_tau_days=14)
result = service.execute_scenario(config)
assert [r.sku_id for r in result.review_list] == ["A", "B", "C"]
assert [(r.sku_id, r.allocated_q) for r in result.order_proposal] == [("B", 14), ("C", 1)]
```

Production UI configuration:

```powershell
$env:MMS_DUCKDB_PATH = 'C:/exports/verified-mms.duckdb'
$env:MMS_ARTIFACT_PATH = 'C:/approved/histgb.joblib'
$env:MMS_MANIFEST_PATH = 'C:/approved/manifest.json'
$env:MMS_DECISIONS_PATH = 'C:/local/mms-decisions.sqlite'
uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/ui.py
```

Without `MMS_DUCKDB_PATH`, the standalone UI explicitly runs in synthetic demo
mode. With a production database configured, errors are surfaced; no demo model
is substituted. Connections are opened read-only per snapshot. Artifact loading
is cached; use immutable versioned paths or restart after deploying a new bundle.

## Service and persistence

- `list_models()` returns four versioned metadata records and parameter names.
- `run_model(model_id, snapshot, parameters)` returns `ModelResult(ok, items,
  metadata, error)`. Unsupported parameters and missing artifacts have structured
  errors. Service calls raise `MMSValidationError`/`ArtifactError` for UI handling.
- `execute_scenario(config)` returns separate Review/Order lists and summary.
- `compare_scenarios(configs)` accepts 2–4 same-date configs, reads one snapshot
  and scores once, then returns overlap, rank/quantity changes and separate plans.
- `Backtester(service, outcome_provider).run(config, dates, horizon_days)` supports
  7/14/30-day windows, per-date results and explicit macro averages of defined
  metrics. Precision@K uses `min(K, cohort size)`, recalls/lift use incident-risk
  cohort positives, and ROC-AUC requires both classes. Existing zero-stock SKUs
  are reported separately. WAPE/Bias use total observed sales as denominator;
  Bias is (predicted-actual)/actual. Zero denominators yield JSON null.
- `DecisionRepository(path).save_decision(result, actions)` / `get_session(id)` /
  `list_sessions()` preserve exact JSON results and manager-entered actions.
  Edited quantities describe a manager override, not a new Q-constrained proposal.
  Follow-up observations do not prove that a manager's decision caused a receipt.
- `add_followups(id, outcome_provider)` requires the entire 30-day window; receipt
  within 7 days and stockout within 30 days are separately sourced observations.

`to_dict()` converts service dataclasses to JSON-compatible values. Timestamps
of saved sessions are UTC; analysis dates are calendar dates in the data contract.

Read [data contract](../../../docs/mms-data-contract.md),
[artifact audit and provisional rules](../../../docs/mms-artifact-audit.md), and
[execution status](../../../docs/mms-progress.md) before production integration.
Historical metrics are observational; neither demo nor retrospective results
establish causal reductions in stockouts, costs or lost sales.
