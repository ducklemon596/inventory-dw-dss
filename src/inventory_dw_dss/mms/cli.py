"""JSON operational checks and explicitly requested, versioned new model training."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

from .core.schemas import MMSValidationError, POLICIES, PROFILES, ScenarioConfig, to_dict
from .data.clickhouse_adapter import audit_warehouse
from .models.targets import RISK_TARGETS, model_target
from .runtime import SourceSettings, build_provider, build_runtime
from .verification import check_artifact, run_reference_suite


def _json_file(path):
    def invalid_constant(value):
        raise MMSValidationError(f"Non-finite JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid_constant)


def readiness(settings, analysis_date):
    checks = []
    snapshot, risk = None, None
    try:
        snapshot = build_provider(settings).get_snapshot(analysis_date)
        checks.append({"check": "snapshot", "ok": True, "data_version": snapshot.data_version,
                       "snapshot_version": snapshot.snapshot_version, "sku_count": len(snapshot.rows)})
    except (MMSValidationError, OSError) as exc:
        checks.append({"check": "snapshot", "ok": False, "message": str(exc)})
    try:
        runtime = build_runtime(settings)
        risk = runtime.service.executor.risk_model
        if snapshot is not None:
            runtime.service.executor.risk_scores(snapshot)
        checks.append({"check": "artifact", "ok": True, "version": risk.version})
    except (MMSValidationError, OSError) as exc:
        checks.append({"check": "artifact", "ok": False, "message": str(exc)})
    synthetic = settings.source == "demo" or getattr(risk,"manifest",{}).get("data_kind") == "synthetic"
    return {"source": settings.source, "synthetic_demo": synthetic,
            "production_ready": settings.source != "demo" and getattr(risk,"manifest",{}).get("data_kind") != "synthetic"
                and all(c["ok"] for c in checks), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description="MMS read-only integration and verification")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("audit-warehouse", help="Inspect existing ClickHouse marts without semantic approval")
    source = commands.add_parser("audit-source", help="Inspect downloaded CSV headers, sequences and observed coverage")
    source.add_argument("--date", required=True)
    source.add_argument("--sales", default="data/raw/sales_raw.csv")
    source.add_argument("--stock", default="data/raw/stock_raw.csv")
    check = commands.add_parser("check-artifact", help="Load only an owner-approved local joblib bundle")
    check.add_argument("--artifact", required=True)
    check.add_argument("--manifest", required=True)
    verify = commands.add_parser("verify-reference", help="Compare original TN/golden cases with pinned versions")
    verify.add_argument("--reference", required=True)
    ready = commands.add_parser("readiness")
    ready.add_argument("--date", required=True)
    bootstrap = commands.add_parser("bootstrap-demo", help="Create a new simulated dataset, trained HistGB, reports and app")
    bootstrap.add_argument("--output", required=True)
    bootstrap.add_argument("--seed", type=int, default=7)
    train = commands.add_parser("train-histgb", help="Train a new model from normalized snapshots and independent future labels")
    train.add_argument("--dates", required=True, help="Comma-separated decision dates")
    train.add_argument("--output", required=True)
    train.add_argument("--artifact-version", required=True)
    train.add_argument("--data-kind", choices=["synthetic", "verified"], required=True)
    train.add_argument("--horizon", type=int, default=7)
    train.add_argument("--seed", type=int, default=7)
    train.add_argument("--feature-set", choices=["basic", "mart"], default="basic",
                       help="basic: 4 canonical features; mart: replenishment mart features (MMS_DATA_SOURCE=mart)")
    train.add_argument("--target", choices=RISK_TARGETS, default="dispensary_stockout",
                       help="pharmacy_shortfall: sales reach all stock at T (purchase risk); "
                            "dispensary_stockout: recorded shelf stockout")
    train.add_argument("--sop-scope", choices=["date", "sku"],
                       help="Stocktake exclusion; defaults to date for basic and sku for mart")
    backtest = commands.add_parser("backtest", help="Score historical dates with the configured artifact and report metrics")
    backtest.add_argument("--dates", required=True, help="Comma-separated decision dates")
    backtest.add_argument("--horizon", type=int, default=14)
    backtest.add_argument("--profile", choices=PROFILES, default="RiskFirst")
    backtest.add_argument("--top-k", type=int, default=50)
    backtest.add_argument("--sop-scope", choices=["date", "sku"], default="sku")
    simulate = commands.add_parser("simulate-policy",
                                   help="Replay replenishment policies over mart history (MMS_DATA_SOURCE=mart)")
    simulate.add_argument("--start", required=True, help="First review date; its orderable products form the cohort")
    simulate.add_argument("--end", required=True)
    simulate.add_argument("--policies", default="coverage:14,coverage:21,coverage:28,service:0.9,service:0.95,service:0.98",
                          help="Comma-separated coverage:<days>, service:<level> or service:abc")
    simulate.add_argument("--lead-time", type=int, default=2)
    simulate.add_argument("--review-days", type=int, default=7)
    simulate.add_argument("--impute-censored", action="store_true", help="Add MA90 demand on recorded empty days")
    scenario = commands.add_parser("scenario")
    scenario.add_argument("--date", required=True)
    scenario.add_argument("--profile", choices=PROFILES, default="RiskFirst")
    scenario.add_argument("--pstar", type=float, default=.3)
    scenario.add_argument("--top-k", type=int, default=50)
    scenario.add_argument("--unit-budget", type=int)
    scenario.add_argument("--coverage-days", type=float, default=14.)
    scenario.add_argument("--policy", choices=POLICIES, default="coverage")
    scenario.add_argument("--service-level", type=float, default=.95)
    scenario.add_argument("--lead-time", type=float, default=2.)
    scenario.add_argument("--abc-service", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "audit-source":
            from .data.raw_audit import audit_source_exports
            payload = {"ok": True, "audit": audit_source_exports(args.sales,args.stock,args.date)}
        elif args.command == "bootstrap-demo":
            from .training import build_synthetic_bundle
            payload = {"ok": True, "bundle": build_synthetic_bundle(args.output, args.seed)}
        elif args.command == "train-histgb":
            from .runtime import MMSRuntime
            from .service import MMSService
            from .training import train_histgb
            settings = SourceSettings.from_env()
            if settings.source == "demo":
                raise MMSValidationError("Training requires normalized DuckDB/ClickHouse data; use bootstrap-demo for simulation")
            provider = build_provider(settings)
            outcomes = MMSRuntime(MMSService(provider), settings).load_outcomes()
            payload = {"ok": True, "training": train_histgb(provider, outcomes,
                [d.strip() for d in args.dates.split(",")], args.output, args.artifact_version,
                data_kind=args.data_kind, horizon_days=args.horizon, seed=args.seed, features_name=args.feature_set,
                sop_scope=args.sop_scope, risk_target=args.target)}
        elif args.command == "backtest":
            from .evaluation.backtesting import Backtester
            runtime = build_runtime()
            dates = [d.strip() for d in args.dates.split(",")]
            # pstar=0 ranks the whole cohort; ranking metrics use top-K regardless of threshold.
            config = ScenarioConfig(dates[0], profile=args.profile, pstar=0, top_k=args.top_k)
            report = Backtester(runtime.service, runtime.load_outcomes()).run(
                config, dates, args.horizon, sop_scope=args.sop_scope)
            payload = {"ok": True, "synthetic_demo": runtime.is_demo,
                       "backtest": {"horizon_days": report.horizon_days,
                                    "risk_target": model_target(runtime.service.executor.risk_model),
                                    "aggregate": report.aggregate,
                                    "per_date": [{k: v for k, v in r.items() if k != "metadata"} for r in report.per_date]}}
        elif args.command == "simulate-policy":
            from .data.mart_adapter import ReplenishmentMartProvider
            from .evaluation import policy_simulation as sim
            settings = SourceSettings.from_env()
            if settings.source != "mart":
                raise MMSValidationError("Policy simulation reads the replenishment marts; set MMS_DATA_SOURCE=mart")
            specs = [sim.parse_policy(p) for p in args.policies.split(",")]
            with closing(settings.connect_clickhouse()) as client:
                provider = ReplenishmentMartProvider(client, settings.database)
                data = sim.load_simulation_data(provider, args.start, args.end)
                version, _ = provider.data_version()
            payload = {"ok": True, "simulation": {
                "data_version": version, "start": args.start, "end": args.end, "products": len(data.product_ids),
                "lead_time_days": args.lead_time, "review_days": args.review_days, "impute_censored": args.impute_censored,
                "recorded": sim.recorded_baseline(data),
                "policies": [sim.simulate(data, s, args.review_days, args.lead_time, args.impute_censored) for s in specs]}}
        elif args.command == "check-artifact":
            payload = {"ok": True, "artifact": check_artifact(args.artifact, args.manifest)}
        elif args.command == "audit-warehouse":
            settings = SourceSettings.from_env()
            with closing(settings.connect_clickhouse()) as client:
                payload = {"ok": True, "audit": audit_warehouse(client, settings.database)}
        elif args.command == "readiness":
            report = readiness(SourceSettings.from_env(), args.date)
            payload = {"ok": report["production_ready"], "readiness": report}
        elif args.command == "verify-reference":
            spec = _json_file(args.reference)
            if not isinstance(spec,dict) or not isinstance(spec.get("cases"),list):
                raise MMSValidationError("Reference cases must be a nonempty list")
            runtime = build_runtime()
            needs_outcomes = isinstance(spec, dict) and any(isinstance(c, dict) and c.get("kind") == "backtest" for c in spec.get("cases", []))
            report = run_reference_suite(runtime.service, spec, runtime.load_outcomes() if needs_outcomes else None)
            payload = {"ok": report["passed"], "synthetic_demo": runtime.is_demo, "reference": report}
        else:
            runtime = build_runtime()
            result = runtime.service.execute_scenario(ScenarioConfig(args.date, profile=args.profile,
                pstar=args.pstar, top_k=args.top_k, unit_budget_q=args.unit_budget, coverage_tau_days=args.coverage_days,
                policy=args.policy, service_level=args.service_level, lead_time_days=args.lead_time,
                abc_service=args.abc_service))
            payload = {"ok": True, "synthetic_demo": runtime.is_demo, "result": to_dict(result)}
        print(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return 0 if payload["ok"] else 1
    except (MMSValidationError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": {"code": "integration_unavailable", "message": str(exc)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
