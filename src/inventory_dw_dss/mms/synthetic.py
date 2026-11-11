"""A reproducible simulation used to exercise training/integration, never source evidence."""
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile

from .core.schemas import MMSValidationError, ScenarioConfig, to_dict
from .data.duckdb_adapter import DuckDBDataProvider
from .evaluation.backtesting import Backtester, Observation, OutcomeProvider
from .models.histgb import HistGBRiskModel
from .service import MMSService
from .tracking.repository import DecisionRepository, ManagerAction
from .training import train_histgb


def _simulation(seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    start, end = date(2025, 1, 1), date(2025, 9, 14)
    sales, inventory, observations = [], [], []
    data_version = f"synthetic-ledger-v1-seed{seed}-32sku"
    for sku_number in range(32):
        sku = f"SIM-{sku_number:03d}"
        rate = 0. if sku_number == 31 else float(rng.uniform(1, 12))
        cycle = int(rng.integers(7, 22))
        stock = max(10, int(rate*cycle))
        last_receipt = 0
        history = []
        for day in range((end-start).days+1):
            t = start+timedelta(days=day)
            receipt = 0
            if day and day % cycle == 0:
                receipt = max(1, int(rate*cycle*rng.uniform(.6, 1.6)))
                stock += receipt
                last_receipt = day
            demand = int(rng.poisson(rate*(1.3 if t.weekday() >= 5 else 1)))
            recorded_sales = min(stock, demand)
            stock -= recorded_sales
            sales.append((sku, t, float(recorded_sales), float(recorded_sales*(sku_number+2))))
            sop = t == date(2025, 8, 1)
            observations.append(Observation(t, sku, float(recorded_sales), stock == 0, float(receipt), sop))
            history.append((stock == 0, sop))
            if day >= 89:
                diagnostic = [zero for zero, is_sop in history[-90:] if not is_sop]
                inventory.append((t, sku, float(stock), "simulation-unit", "pharmacy_total",
                    f"synthetic-snapshot-v1-seed{seed}-{t}", data_version, t, True, "{}",
                    day-last_receipt, ["sop_excluded_diagnostics"], sum(diagnostic), len(diagnostic)))
    return inventory, sales, OutcomeProvider(observations, end, f"synthetic-labels-v1-seed{seed}")


def build_bundle(output_directory, seed=7):
    import duckdb
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise MMSValidationError("Synthetic seed must be an integer in [0,2**32-1]")
    target = Path(output_directory).resolve()
    if target.exists():
        raise MMSValidationError("Synthetic bundle output directory already exists; use a new version path")
    inventory, sales, outcomes = _simulation(seed)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mms-simulation-", dir=target.parent) as temporary:
        staged = Path(temporary)/"bundle"
        staged.mkdir()
        database = staged/"data.duckdb"
        with duckdb.connect(str(database)) as c:
            c.execute("BEGIN TRANSACTION")
            c.execute("CREATE TABLE mms_inventory_daily (analysis_date DATE, sku_id VARCHAR, available_stock DOUBLE, stock_unit VARCHAR, location_scope VARCHAR, snapshot_version VARCHAR, data_version VARCHAR, feature_as_of DATE, eligible BOOLEAN, features VARCHAR, days_since_last_receipt INTEGER, flags VARCHAR[], observed_stockout_days INTEGER, diagnostic_observed_days INTEGER)")
            c.executemany("INSERT INTO mms_inventory_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", inventory)
            c.execute("CREATE TABLE mms_sales_daily (sku_id VARCHAR, sales_date DATE, quantity DOUBLE, revenue DOUBLE)")
            c.executemany("INSERT INTO mms_sales_daily VALUES (?,?,?,?)", sales)
            c.execute("CREATE TABLE mms_outcome_metadata (data_cutoff DATE, outcome_version VARCHAR)")
            c.execute("INSERT INTO mms_outcome_metadata VALUES (?,?)", [outcomes.data_cutoff, outcomes.version])
            c.execute("CREATE TABLE mms_outcomes_daily (observation_date DATE, sku_id VARCHAR, sales_quantity DOUBLE, stockout BOOLEAN, received_quantity DOUBLE, sop_day BOOLEAN)")
            c.executemany("INSERT INTO mms_outcomes_daily VALUES (?,?,?,?,?,?)", [
                (o.observation_date,o.sku_id,o.sales_quantity,o.stockout,o.received_quantity,o.sop_day) for o in outcomes.observations])
            c.execute("COMMIT")
        provider = DuckDBDataProvider(database)
        training_dates = [date(2025, 4, 1)+timedelta(days=7*i) for i in range(9)]
        trained = train_histgb(provider, outcomes, training_dates, staged/"artifact",
            f"new-synthetic-histgb-v1-seed{seed}", data_kind="synthetic", seed=seed)
        model = HistGBRiskModel.load(trained["artifact"], trained["manifest"])
        service = MMSService(provider, model)
        config = ScenarioConfig("2025-06-30", pstar=0, top_k=12, unit_budget_q=150)
        profiles = [replace(config, profile=p) for p in ("RiskFirst", "LowStock", "DOS", "RevenueAtRisk")]
        comparison = service.compare_scenarios(profiles)
        reports = {str(h): to_dict(Backtester(service, outcomes).run(config,
            ["2025-06-30", "2025-07-14", "2025-08-15"], h)) for h in (7, 14, 30)}
        variants = service.compare_scenarios([config, replace(config, pstar=.8),
            replace(config, top_k=5, unit_budget_q=30), replace(config, coverage_tau_days=30)])
        result = comparison.results[0]
        repository = DecisionRepository(staged/"decisions.sqlite")
        actions = [ManagerAction(result.review_list[0].sku_id, "accepted", note="Synthetic workflow example")]
        session = repository.save_decision(result, actions)
        repository.add_followups(session["session_id"], outcomes)
        snapshot = provider.get_snapshot(config.analysis_date)
        versions = {"artifact_version": model.version, "data_version": snapshot.data_version,
                    "snapshot_versions": {str(config.analysis_date): snapshot.snapshot_version}}
        cases = [{"name": f"NEW-profile-{r.config.profile}", "kind": "scenario", "config": to_dict(r.config),
            "cohort_sku_ids": [s.sku_id for s in snapshot.rows], "versions": versions,
            "expected": {"review_skus": [i.sku_id for i in r.review_list],
                         "order_units": {i.sku_id: i.allocated_q for i in r.order_proposal}}} for r in comparison.results]
        reference = {"schema_version": "mms-reference-v1", "reference_id": f"NEW-synthetic-regression-v1-seed{seed}",
            "provenance": "New generated regression baseline from current implementation; not independent TN evidence",
            "absolute_tolerance": 1e-8, "cases": cases}
        (staged/"reference.json").write_text(json.dumps(reference, indent=2, allow_nan=False), encoding="utf-8")
        experiment = {"data_kind": "synthetic", "original_tn_reproduction": False, "seed": seed,
            "NEW1_ma90_and_NEW2_histgb": reports, "NEW3_coverage_and_NEW4_profiles": to_dict(comparison),
            "NEW5_constraints": to_dict(variants),
            "NEW6_diagnostics": [{"sku_id": i.sku_id, "flags": list(i.flags)} for i in service.execute_scenario(replace(config,top_k=50)).review_list if i.flags],
            "NEW7_tracking": repository.get_session(session["session_id"])}
        (staged/"new-experiments.json").write_text(json.dumps(experiment,indent=2,allow_nan=False),encoding="utf-8")
        (staged/"app.py").write_text('''from pathlib import Path
import streamlit as st
from inventory_dw_dss.mms.runtime import SourceSettings, build_runtime
from inventory_dw_dss.mms.ui import render
@st.cache_resource
def application_runtime():
    root = Path(__file__).resolve().parent
    return build_runtime(SourceSettings(source="duckdb", duckdb_path=str(root/"data.duckdb"),
        artifact_path=str(root/"artifact/histgb.joblib"), manifest_path=str(root/"artifact/manifest.json")))
render(application_runtime=application_runtime())
''', encoding="utf-8")
        staged.rename(target)
    return {"data_kind": "synthetic", "original_tn_reproduction": False, "database": str(target/"data.duckdb"),
        "artifact": str(target/"artifact/histgb.joblib"), "manifest": str(target/"artifact/manifest.json"),
        "reference": str(target/"reference.json"), "experiments": str(target/"new-experiments.json"),
        "streamlit_script": str(target/"app.py"), "supervised_data_cutoff": trained["supervised_data_cutoff"]}
