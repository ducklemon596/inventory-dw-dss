# Existing asset audit

Audited the checked-out repository before implementation. No trained artifact
or TN scripts were found among tracked/untracked project source files.

| Requested asset | Repository finding / consequence |
| --- | --- |
| common.py, exp5_scenarios.py, exp7_diagnostics.py | Absent; TN-specific equations and thresholds cannot be verified |
| interactive_lab.py | Absent; original baseline cannot be run |
| Trained HistGB / feature list / preprocessing | Absent; production MB2 intentionally errors without approved inputs |
| TN1–TN7 numerical reports | Absent; numerical reproduction and significance claims remain unverified |
| DuckDB analytics database | Absent; actual mart implementation is ClickHouse |
| Existing Streamlit application | Absent; supplied a standalone service-backed integration page |
| Three source PDFs / research summary cited in plan | Absent from checkout; plan is the available specification |

The warehouse preserves sparse observed daily balances and original/conversion
provenance, not verified pharmacy-wide available-stock snapshots. There is no
safe automatic mapping to the proposed snapshot schema without an export contract.
See [data contract](mms-data-contract.md).

## Trusted HistGB bundle

Use an owner-approved local joblib artifact. Deserializing joblib/pickle can
execute code; an untrusted file is not made safe by its checksum. Production
does not accept uploads or train a substitute model. The independent manifest
must contain:

```json
{
  "artifact_version": "owner-assigned-immutable-version",
  "sklearn_version": "exact-training-environment-version",
  "sha256": "actual-sha256-of-approved-joblib-file",
  "features": ["sales_90d", "available_stock"],
  "positive_class": 1,
  "preprocessing": "embedded",
  "calibrated": false,
  "compatible_data_versions": ["approved-export-data-version"],
  "supervised_data_cutoff": "2025-05-31"
}
```

The example feature list is illustrative, **not** the TN feature schema. Supply
the original ordered list and preserve any preprocessing in the saved Pipeline.
Feature names/order must match `feature_names_in_`; the final estimator must be
HistGradientBoostingClassifier. Required finite features must be present; canonical
values cannot be silently overridden by extra features. Missing DOS/receipt
history requires an original compatible preprocessing contract, not zero filling.
The scikit-learn runtime version must exactly match the manifest. Adjust the MMS
environment to that version for a real artifact and rerun inference tests.
Inference rejects snapshot data versions outside the explicitly approved list.
The supervised-data cutoff must include the latest **features and outcome labels**
used in training, tuning, model selection and calibration. It must be at/before
the decision date for historical inference; a future-trained artifact is rejected.
The owner must verify this declaration against the actual experimental split.
The cutoff is retained in model/scenario/backtest metadata. It cannot certify
an unverified training history merely because a manifest supplies a date.

Scores are called risk scores. A manifest calibration declaration must be backed
by the experimental owner's held-out calibration evidence before interpreting
scores as calibrated probabilities. The synthetic demo uses fixed named scores
and is visibly marked; test-only HistGB training is confined to a temporary test.

## Provisional policy choices pending TN code

- MB3: `max(0, ceil(tau*sales_90d/90 - stock))`; zero sales, ineligible SKU or
  negative stock implies q=0. No lead-time/MOQ/purchasing optimization.
- All profiles: retain risk >= pstar, sort by profile, then take at most K.
  RiskFirst sorts descending risk; LowStock ascending stock; DOS ascending
  coverage (undefined last); RevenueAtRisk descending risk × 90-day revenue proxy.
  Ties use SKU ID ascending.
- Q allocation visits this list in rank order, giving `min(suggested, remaining)`
  including partial fills. It is reproducible greedy allocation, not an optimum.
- Review retains zero-quantity alerts; Order contains eligible items with positive
  suggested **and allocated** quantities.
- Stagnant: positive stock and zero 90-day sales. Chronic: at least 30 verified
  SOP-excluded observation days and at least 80% stockout days. Demand spike:
  last-seven-day sales > twice the MA90 seven-day expectation, informational only.

These decisions do not assert equivalence with TN5/TN6/TN7. Replace them only
after the original definitions are available, with regression examples.
