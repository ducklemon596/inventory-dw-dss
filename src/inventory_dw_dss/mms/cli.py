"""inventory-mms: train, evaluate and run replenishment plans on the marts. Output is JSON."""
import argparse
from datetime import timedelta
import json
import sys

from .schemas import POLICIES, PROFILES, MMSError, ScenarioConfig, as_date, to_dict


def mondays(start, end):
    """Comma-separated Mondays from start to end (inclusive), for --dates."""
    t, end = as_date(start), as_date(end)
    t += timedelta(days=-t.weekday() % 7)
    out = []
    while t <= end:
        out.append(str(t))
        t += timedelta(weeks=1)
    return out


def date_list(text):
    """'2025-06-02,2025-06-09' or a weekly range '2025-06-02..2025-12-15'."""
    if ".." in text:
        return mondays(*text.split(".."))
    return [d.strip() for d in text.split(",") if d.strip()]


def plan_options(parser):
    parser.add_argument("--profile", choices=PROFILES, default="RiskFirst")
    parser.add_argument("--pstar", type=float, default=.3)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--unit-budget", type=int)
    parser.add_argument("--policy", choices=POLICIES, default="service_level")
    parser.add_argument("--coverage-days", type=float, default=7.)
    parser.add_argument("--service-level", type=float, default=.95)
    parser.add_argument("--lead-time", type=float, default=2.)
    parser.add_argument("--abc-service", action="store_true")


def config_from(args, analysis_date, **overrides):
    values = dict(profile=args.profile, pstar=args.pstar, top_k=args.top_k, unit_budget=args.unit_budget,
                  policy=args.policy, coverage_days=args.coverage_days, service_level=args.service_level,
                  lead_time_days=args.lead_time, abc_service=args.abc_service)
    return ScenarioConfig(analysis_date, **(values | overrides))


def build_parser():
    from .models.targets import RISK_TARGETS
    parser = argparse.ArgumentParser(prog="inventory-mms", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    train = commands.add_parser("train", help="Train the risk model on past decision dates")
    train.add_argument("--dates", required=True, help="Comma list or weekly range START..END")
    train.add_argument("--output", required=True, help="New directory for histgb.joblib + manifest.json")
    train.add_argument("--version", required=True, help="Model version label stored in the manifest")
    train.add_argument("--horizon", type=int, choices=(7, 14, 30), default=14)
    train.add_argument("--target", choices=RISK_TARGETS, default="pharmacy_shortfall")

    backtest = commands.add_parser("backtest", help="Risk and demand metrics on past dates (uses MMS_ARTIFACT_PATH)")
    backtest.add_argument("--dates", required=True)
    backtest.add_argument("--horizon", type=int, choices=(7, 14, 30), default=14)
    plan_options(backtest)

    simulate = commands.add_parser("simulate-policy", help="Replay order policies over mart history")
    simulate.add_argument("--start", required=True, help="First review date; its orderable products form the cohort")
    simulate.add_argument("--end", required=True)
    simulate.add_argument("--policies", default="coverage:14,coverage:21,coverage:28,service:0.9,service:0.95,service:0.98",
                          help="Comma list of coverage:<days>, service:<level> or service:abc")
    simulate.add_argument("--lead-time", type=int, default=2)
    simulate.add_argument("--review-days", type=int, default=7)
    simulate.add_argument("--impute-censored", action="store_true", help="Add MA90 demand on recorded empty days")

    plan = commands.add_parser("plan", help="Review list and order proposal for one date")
    plan.add_argument("--date", required=True)
    plan_options(plan)
    return parser


def run(args):
    if args.command == "train":
        from .data import MartReader
        from .training import train
        reader = MartReader()
        return train(reader, reader.outcomes(), date_list(args.dates), args.output, args.version,
                     horizon_days=args.horizon, target=args.target)
    if args.command == "simulate-policy":
        from .data import MartReader
        from .evaluation import policy_simulation as sim
        reader = MartReader()
        data = sim.load_simulation_data(reader, args.start, args.end)
        return {"products": len(data.product_ids), "lead_time_days": args.lead_time,
                "review_days": args.review_days, "impute_censored": args.impute_censored,
                "recorded": sim.recorded_baseline(data),
                "policies": [sim.simulate(data, sim.parse_policy(p), args.review_days, args.lead_time,
                                          args.impute_censored) for p in args.policies.split(",")]}
    from .service import MMSService
    service = MMSService.from_env()
    if args.command == "backtest":
        from .evaluation.backtesting import Backtester
        dates = date_list(args.dates)
        # pstar 0 keeps every product, so ranking metrics see the whole cohort.
        report = Backtester(service, service.reader.outcomes()).run(config_from(args, dates[0], pstar=0.),
                                                                     dates, args.horizon)
        return {"horizon_days": report.horizon_days, "risk_target": report.target,
                "aggregate": report.aggregate, "per_date": report.per_date}
    return to_dict(service.plan(config_from(args, args.date)))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        payload = {"ok": True, "result": run(args)}
    except (MMSError, OSError) as exc:
        payload = {"ok": False, "error": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, default=str))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
