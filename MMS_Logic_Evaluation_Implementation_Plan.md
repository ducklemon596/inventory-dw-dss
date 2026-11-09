# MMS Logic & Evaluation — Implementation Plan (M5 + M6)

**Project:** IRPD — Logistics / Inventory Decision Support System (CO4031)  
**Scope:** Model Management Subsystem (MMS) Logic + Model Evaluation + Decision Tracking  
**Owner:** Thoại (M5 logic + M6)  
**Target timeline:** 09/11–10/12/2026; 11–13/12 reserved for final integration fixes and submission  
**Final submission deadline:** 23:00, 13/12/2026 (per course project description)  
**Status:** Backend and standalone synthetic Streamlit demo implemented; see the [execution ledger](docs/mms-progress.md) for verified steps and external dependencies. Production/TN acceptance is not yet complete.

## 1. Goals and scope

Build a reusable **Python MMS backend** that Streamlit can call to:

1. Load historical, *as-of-T* inventory and sales features from the data warehouse.
2. Run four documented Model Base components (MB1–MB4).
3. Choose, configure, and compare decision scenarios with constraints on review capacity **K** and replenishment quantity **Q**.
4. Separate the **Review List** (items requiring investigation, including `q = 0`) from the **Order Proposal** (eligible items with `q > 0`).
5. Evaluate model/scenario results on historical dates without future-data leakage.
6. Save decisions, user actions, versions, and later follow-up observations.

**Non-goals:** Automatic purchase-order issuance; purchasing-cost optimization / EOQ; causal claims that a chosen policy reduces stockouts; training an additional ML model merely to enlarge the model catalog.

**Alignment with the experimental summary:** Prioritize the four validated functions **MA90 + HistGB + Coverage-based Replenishment + Scenario & Resource Allocation**. Reuse and verify existing TN1–TN7 experiments and `interactive_lab.py` rather than rewriting a working prototype from scratch.

## 2. Architecture and module responsibilities

```text
                Streamlit DSS UI (Phương)
                          |
                          v
        +-------------------------------------+
        |         MMS API / Service           |
        | Model Directory | Model Manager     |
        | Model Executor  | Scenario Compare  |
        +-------------------------------------+
           |          |         |         |
           v          v         v         v
         MB1         MB2       MB3       MB4
         MA90       HistGB    Coverage   Allocation
           \          |         |         /
            +---------+---------+--------+
                          |
               Backtesting / Metrics
                          |
                 Decision Tracking
                          ^
                          |
       DuckDB / Analytical Marts (Quang)
  inventory snapshots, sales, stockout history
```

### 2.1 Model Base (MB1–MB4)

| Model | Method | Main input | Main output | Implementation note |
|---|---|---|---|---|
| **MB1 — Demand Forecasting** | 90-day moving average (**MA90**) | As-of sales history | `vel90`, demand forecast for 30 days | Reuse TN1 logic; handle low/zero sales clearly |
| **MB2 — Stockout Risk** | **HistGradientBoosting (HistGB)** classifier | Verified as-of feature set | Stockout risk score, risk ranking | Reuse trained artifact and exact preprocessing/feature order; check probability calibration before interpreting score as a calibrated probability |
| **MB3 — Coverage-based Replenishment** | `q ≈ max(0, ceil(tau * vel90 - available_stock))` | Inventory, velocity, `tau` | Suggested units `q` | Formula is illustrative until rounding and eligibility rules are verified against source code |
| **MB4 — Scenario & Resource Allocation** | Profiles and selection rules | MB1–MB3 outputs, `K`, `Q`, `pstar`, `tau` | Review List, Order Proposal, plan metrics | Add Q to scenario engine; compare 2–4 scenarios |

**Profiles used by MB4:** `RiskFirst`, `LowStock`, `DOS`, `RevenueAtRisk`.

**Important:** `K` means the maximum number of SKU review slots. `Q` means the maximum total **units of inventory** available for allocation, **not money**. `pstar` is a risk threshold; `tau` is the requested days of stock coverage. If both `pstar` and `K` are used, document their application order.

### 2.2 MMS core components

- **Model Directory:** A registry for model ID, name, version, description, required inputs, parameters, outputs, and a callable reference.
- **Model Manager:** Register and retrieve models; validate model-specific parameters and compatible datasets/versions.
- **Model Executor:** Resolve model and dependencies, retrieve a consistent snapshot, execute, normalize outputs, and capture execution metadata.
- **Scenario Comparison:** Run scenarios using the **same as-of data snapshot** and produce differences in selected SKUs, rankings, proposed quantities, resource use, and historical metrics when available.
- **Backtesting:** Run consistent historical evaluations and label windows; report metrics without leakage.
- **Decision Tracking:** Persist decision configuration, results, manager actions, and follow-up observations (without conflating a manager-reported action with an inferred historical receipt).

## 3. Delivery roadmap

| Phase | Target dates | Main deliverables | Exit criteria |
|---|---|---|---|
| **P1 — Data Contract & Existing Code Audit** | 09–15/11 | Inventory snapshot schema, DuckDB adapter, available HistGB artifact audit, test fixtures | `get_snapshot(T)` works; features are consistent and do not use future information |
| **P2 — Model Base & MMS Core** | 16–22/11 | Reusable MB1–MB3, Directory, Manager, Executor | One API can execute models and return stable, explainable outputs |
| **P3 — Scenario Engine (MB4)** | 23–29/11 | Four profiles, `pstar/K/Q/tau`, comparison, Review vs Order | Plans respect `K/Q`; changes in configuration change decisions correctly |
| **P4 — Backtesting & Decision Tracking** | 30/11–06/12 | Evaluation pipeline, metrics, saved decision sessions | Results can be reproduced by date/model/data version; decisions can be retrieved |
| **P5 — Integration & Testing** | 07–10/12 | End-to-end Streamlit integration, tests, documented demo scenario | Manager can configure, compare, approve/reject, save and revisit a plan |
| **Buffer / Submission** | 11–13/12 | Fixes, report, screenshots, demo video and slides | Submission materials are ready by the official deadline |

The dates are planning estimates. Parallelize with the Data Warehouse and UI teams whenever possible; use a **mock snapshot** while waiting for DuckDB marts.

## 4. Detailed implementation tasks

### P1. Data Contract & Existing Code Audit

- [ ] Request and inspect available code/artifacts: `common.py`, `exp5_scenarios.py`, `exp7_diagnostics.py`, `interactive_lab.py`, trained HistGB artifact, feature list, preprocessing code, and experimental reports.
- [ ] Confirm historical input schema and SKU eligibility rules with the Data Engineering owner.
- [ ] Confirm the **stock definition at pharmacy level** across Apotek and Gudang Obat 1; do not assume a stockout at one location means a stockout for the pharmacy.
- [ ] Identify SOP/stocktaking transactions and rules to avoid false zero-stock labels, especially **SOP202508**.
- [ ] Implement `DuckDBDataProvider.get_snapshot(date, filters)` and an equivalent mock provider for unit tests.
- [ ] Validate missing data, zero demand, negative balances, duplicate events, and available feature dates.
- [ ] Fix deterministic sort tie-breakers (e.g., `sku_id`) and version identifiers.

**Suggested minimum analytical data contract** (field names to confirm with Quang):

```python
InventorySnapshot = {
    "analysis_date": "2025-06-30",
    "snapshot_version": "...",
    "sku_id": "...",
    "location_scope": "pharmacy_total",
    "available_stock": 30,
    "sales_7d": 12,
    "sales_30d": 40,
    "sales_90d": 90,
    "vel90": 1.0,
    "dos": 30.0,
    "revenue_90d": 1234.5,
    "days_since_last_receipt": 15,
    # Other HistGB features must match the existing trained artifact.
}
```

This is a **proposed interface example**, not an assertion that these exact columns are already present in DuckDB.

**Deliverables:** `data_contract.md`, `duckdb_adapter.py`, mock fixture, artifact audit notes.

### P2. Model Base & MMS Core

- [ ] Wrap MA90 calculation as MB1 and test 90-day lookback boundaries.
- [ ] Load the HistGB model and exact feature/preprocessing contract as MB2; avoid silent feature-order mismatch or unintended retraining.
- [ ] Wrap coverage-based `q` calculations as MB3; verify numeric behavior, rounding and eligibility against experimental code.
- [ ] Register MB1–MB4 metadata in Model Directory.
- [ ] Implement configuration validation in Model Manager; `pstar` in [0,1], `K > 0`, `Q >= 0`, `tau > 0`, valid analysis dates.
- [ ] Implement Model Executor with standardized output, structured errors and execution metadata.
- [ ] Unit-test same snapshot/model/config/version returning the same result.

**Suggested service boundary:**

```python
list_models() -> list[ModelMetadata]
run_model(model_id, snapshot, parameters) -> ModelResult
execute_scenario(config: ScenarioConfig) -> ScenarioResult
compare_scenarios(configs: list[ScenarioConfig]) -> ScenarioComparison
run_backtest(config, decision_dates, horizon_days) -> BacktestReport
save_decision(session, actions) -> DecisionSession
```

### P3. Scenario Engine (MB4)

- [ ] Implement `RiskFirst`, `LowStock`, `DOS`, `RevenueAtRisk` ranking policies using definitions in the verified TN5–TN6 code.
- [ ] Implement `pstar` alert filtering and `K` review limit with documented order of operations.
- [ ] Implement `tau`-dependent `q` calculation via MB3.
- [ ] Integrate `Q` **unit-budget** allocation with a clearly documented selection rule. Start with a reproducible greedy method only if it is consistent with TN6; do not claim it is globally optimal.
- [ ] Output **Review List** (can include risk alerts with `q = 0`).
- [ ] Output **Order Proposal** as an eligible subset with `q > 0`; ensure total quantity is `<= Q` when Q is set.
- [ ] Attach diagnostic flags for **Stagnant Inventory** and **Chronic Stockout** (with SOP-day exclusions). Keep **Demand Spike** informational only.
- [ ] Return plan-level summary: selected SKU count, units suggested, units allocated, budget remaining, stockout-oriented ranking indicators, and overlap among comparison plans.
- [ ] Support comparing 2–4 scenarios against one frozen snapshot.

**Critical tests:** 

- [ ] `q == 0` SKU may remain in Review List but cannot appear in Order Proposal.
- [ ] `sum(allocated_q) <= Q` and review-list count `<= K` when those limits apply.
- [ ] Identical scenario inputs yield identical lists and ordering.
- [ ] A change to `tau`, `pstar`, `K` or `Q` changes outputs only in the expected way.
- [ ] Avoid presenting high risk as an instruction to automatically purchase stock.

### P4. Backtesting & Decision Tracking

**Backtesting**

- [ ] Reconstruct inputs at historical T using only data at/before T.
- [ ] Apply independent future windows of 7, 14 or 30 days for observed outcomes.
- [ ] Separate existing stockouts at T from new stockouts following T.
- [ ] Reproduce/compare experiments against documented TN results on the same cohort, dates and label definitions.
- [ ] Report MB1: **WAPE, Bias**; MB2: **Precision@K, Recall@K, Lift, ROC-AUC**; MB3/MB4: quantity distribution, `q=0` frequency, stockout coverage, resource use and plan overlap.
- [ ] Exclude or report separately the affected **31/07/2025** decision date due to SOP202508 in the 30-day outcome window.
- [ ] Where possible, present both per-date results and aggregate results. Do not claim model improvements are statistically significant unless verified with the matching test design.

**Decision Tracking**

Proposed storage (SQLite for MVP, PostgreSQL if the application stack already has a shared DB):

| Table | Content |
|---|---|
| `decision_sessions` | Session ID, T, model and artifact version, data snapshot version, profile, `pstar`, `K`, `Q`, `tau`, timestamps |
| `decision_items` | SKU, rank, risk score, stock, DOS, recommended `q`, allocated `q`, manager action, note |
| `decision_followups` | Observed receipt within 7 days, observed stockout within 30 days, observation source and data cutoff |

- [ ] Save and retrieve sessions including the exact scenario configuration.
- [ ] Track accepted/rejected/edited suggestions and explanations.
- [ ] Allow historical follow-up only when the full observation window exists.
- [ ] Distinguish actions **entered by a manager** from actions **inferred from transaction records**.
- [ ] Record enough version metadata to reproduce a saved run when the corresponding artifact/data snapshot still exists.

### P5. Streamlit Integration & End-to-End Tests

- [ ] Agree service function signatures and JSON-like schemas with Phương.
- [ ] Model catalog and parameter form call MMS, not reimplement model logic in UI.
- [ ] Display Review List and Order Proposal as separate views.
- [ ] Support 2–4 scenario comparison, stockout metrics, quantity constraints and SKU-level explanations.
- [ ] Expose session save/reopen and manager notes.
- [ ] Verify UI parameter changes do **not** trigger a full dbt/warehouse rebuild.
- [ ] Prepare a deterministic demo using an available historical date (e.g., `2025-06-30`) and fixed artifact version.

## 5. Suggested repository layout

```text
mms/
├── core/
│   ├── schemas.py
│   ├── directory.py
│   ├── manager.py
│   └── executor.py
├── models/
│   ├── ma90.py
│   ├── histgb.py
│   ├── replenishment.py
│   └── scenario.py
├── data/
│   └── duckdb_adapter.py
├── evaluation/
│   ├── backtesting.py
│   ├── metrics.py
│   └── scenario_comparison.py
├── tracking/
│   └── repository.py
├── diagnostics/
│   ├── stagnant.py
│   ├── chronic.py
│   └── demand_spike.py
└── tests/
    ├── test_models.py
    ├── test_executor.py
    ├── test_scenarios.py
    ├── test_backtesting.py
    └── test_tracking.py
```

**Technology choices:** Python, pandas, DuckDB, Pydantic or dataclasses, scikit-learn for compatible inference/metrics, pytest, and SQLite/PostgreSQL for tracking. FastAPI and microservices are **not required** for this scope.

## 6. External dependencies and coordination

**Need from Quang (Data Warehouse):**

- DuckDB/table schemas and sample as-of snapshots.
- Daily inventory and sales data, stockout labels, stocktaking/SOP flags and data versions.
- Clarification of SKU eligibility, available inventory at pharmacy level and location aggregation.

**Need from Phương (UI):**

- Agreement on model catalog, scenario input, ranking output, side-by-side comparisons, Review/Order UX, and saved-session UI.
- Common rules on validation and displaying incomplete historical follow-up windows.

**Need from the experimental owner / team repository:**

- All experiment scripts, trained HistGB artifact, preprocessing and feature schema, and documented TN1–TN7 result files.
- The `interactive_lab.py` prototype and exact rules used for TN6 Q allocations and diagnostic flags.

## 7. Acceptance checklist

- [ ] Four Model Base components registered and executable.
- [ ] Model Directory displays accurate metadata, parameter definitions and versions.
- [ ] Model Manager validates configurations and routes requests correctly.
- [ ] Executor uses consistent as-of data and produces stable, explainable results.
- [ ] MB4 supports `RiskFirst`, `LowStock`, `DOS`, `RevenueAtRisk` and `pstar/K/Q/tau`.
- [ ] Review List and Order Proposal obey eligibility, `q>0`, `K` and `Q` invariants.
- [ ] Historical evaluation uses no future features and explicitly addresses stocktaking artifacts.
- [ ] Metrics are computed reproducibly and accompanied by correct interpretation.
- [ ] Decision Tracking saves, retrieves and follows up sessions with version metadata.
- [ ] End-to-end workflow runs through Streamlit without re-running the ETL on every parameter change.
- [ ] Unit/integration tests pass and a reproducible demo scenario is documented.

## 8. First 3 days — concrete starting checklist

**Day 1 — Audit:**
- [ ] Run `interactive_lab.py` as documented and save baseline outputs.
- [ ] Check what can be reused from TN1–TN7 and identify missing artifacts.
- [ ] Confirm HistGB loads and outputs scores for the documented feature set.

**Day 2 — Data Contract:**
- [ ] Meet Quang to align snapshot schema, stockout semantics and SOP exceptions.
- [ ] Build a mock snapshot and design service input/output schemas.
- [ ] Establish unit tests for zero demand, negative balances and `q=0`.

**Day 3 — First MVP:**
- [ ] Implement model registration and `execute_scenario()` skeleton.
- [ ] Connect MA90, HistGB and the coverage calculation where artifacts permit.
- [ ] Produce one deterministic Review List + Order Proposal at historical T.

**First MVP completion condition:**

```python
config = {
    "analysis_date": "2025-06-30",
    "profile": "RiskFirst",
    "pstar": 0.3,
    "top_k": 50,
    "unit_budget_q": 5000,
    "coverage_tau_days": 14,
}
result = execute_scenario(config)
# result.review_list, result.order_proposal, result.summary
```

This is a **proposed API contract**, not executable code from the current repository.

## 9. Research and reporting cautions

- **MA90 forecasts demand**, **HistGB ranks stockout risk**, **MB3 estimates replenishment units**, **MB4 makes a constrained decision plan**. Do not describe these as four independently trained ML models.
- An alert of high risk does not automatically imply `q > 0` or a justified purchase.
- Historical model metrics are observational; do not claim that the new policy will causally reduce stockouts, lost sales or costs.
- The `Q` constraint is an inventory **unit budget**, not a monetary purchasing budget.
- Because supplier lead times, MOQ, purchasing cost and full purchasing data are incomplete, purchasing optimization is outside the project scope.
- Clearly distinguish experimental results already reported from new integration/backend functionality that is yet to be implemented.

## 10. Source documents

1. **IRPD | Model Base — Kết quả TN1–TN7 & hướng thử nghiệm** (user-provided experimental summary, especially sections 4–14). This plan follows its MB1–MB4 definitions and P0/P1 priorities.
2. **Group5_Logistics_MMS.pdf** — *Midterm Project Proposal*, especially sections 3.1–3.9 (MMS architecture) and 4.2 (team responsibilities). The initial proposal's ranking-model descriptions predate the expanded TN1–TN7 Model Base; align final slides and report to the selected implementation scope.
3. **DW-DSSs_Project Description_TN_261_20260828.pdf** — official course requirements, application assessment rubric and final submission deadline.

---

**Recommended execution priority:** Audit existing assets → Data Contract → MB1–MB3 + MMS Core → MB4/Review/Order/Q → Backtesting → Decision Tracking → Streamlit integration → complete demonstration.
