"""Score past decision dates and compare with what happened next.

Risk metrics use the top_k products by risk score among those holding the target stock;
products whose window contains a stocktake are left out, as in training.

    precision_at_k  share of the top_k that had the event (how many alerts were right)
    recall_at_k     share of all events caught by the top_k
    lift            precision_at_k / event rate (how much better than picking at random)
    roc_auc         probability a random event product scores above a random non-event one
    wape            sum |forecast - actual| / sum actual for MA90 demand over the horizon
    bias            sum (forecast - actual) / sum actual; positive means over-forecast
"""
from dataclasses import dataclass, replace

from ..models.scenario import build_plan
from ..models.targets import target_label, target_stock
from ..schemas import MMSError, as_date


def risk_metrics(labels, scores, k):
    from sklearn.metrics import roc_auc_score
    order = sorted(range(len(labels)), key=lambda i: -scores[i])[:k]
    events = sum(labels)
    hits = sum(labels[i] for i in order)
    precision = hits / len(order) if order else None
    rate = events / len(labels) if labels else None
    return {"precision_at_k": precision, "recall_at_k": hits / events if events else None,
            "lift": precision / rate if precision is not None and rate else None,
            "roc_auc": float(roc_auc_score(labels, scores)) if len(set(labels)) == 2 else None,
            "cohort": len(labels), "events": events}


def demand_metrics(actual, forecast):
    total = sum(actual)
    if not total:
        return {"wape": None, "bias": None}
    return {"wape": sum(abs(f - a) for a, f in zip(actual, forecast)) / total,
            "bias": sum(f - a for a, f in zip(actual, forecast)) / total}


@dataclass(frozen=True)
class BacktestReport:
    horizon_days: int
    target: str
    per_date: tuple[dict, ...]
    aggregate: dict


class Backtester:
    def __init__(self, service, outcomes):
        self.service = service
        self.outcomes = outcomes

    def run(self, config, decision_dates, horizon_days):
        target = self.service.risk_model.target
        per_date = []
        for t in sorted({as_date(d) for d in decision_dates}):
            snapshot = self.service.reader.snapshot(t)
            try:
                future = self.outcomes.window(t, [r.sku_id for r in snapshot.rows], horizon_days)
            except MMSError as exc:
                per_date.append({"date": str(t), "status": "incomplete", "reason": str(exc)})
                continue
            scores = self.service.scores(snapshot)
            cohort = [(r, s) for r, s in zip(snapshot.rows, scores)
                      if target_stock(r, target) > 0 and not any(o.stocktake for o in future[r.sku_id])]
            labels = [target_label(r, future[r.sku_id], target) for r, _ in cohort]
            plan = build_plan(snapshot, replace(config, analysis_date=t), scores)
            events = {r.sku_id for (r, _), y in zip(cohort, labels) if y}
            reviewed = {i.sku_id for i in plan.items}
            actual = [sum(o.sales_quantity for o in future[r.sku_id]) for r in snapshot.rows]
            per_date.append({
                "date": str(t), "status": "evaluated",
                "risk": risk_metrics(labels, [s for _, s in cohort], config.top_k),
                "demand": demand_metrics(actual, [r.daily_demand * horizon_days for r in snapshot.rows]),
                # Share of events that the plan's review list (after pstar and profile) contains.
                "review_coverage": len(reviewed & events) / len(events) if events else None,
            })
        evaluated = [r for r in per_date if r["status"] == "evaluated"]
        aggregate = {"evaluated_dates": len(evaluated)}
        for group, keys in (("risk", ("precision_at_k", "recall_at_k", "lift", "roc_auc")),
                            ("demand", ("wape", "bias"))):
            for key in keys:
                values = [r[group][key] for r in evaluated if r[group][key] is not None]
                aggregate[key] = sum(values) / len(values) if values else None
        coverage = [r["review_coverage"] for r in evaluated if r["review_coverage"] is not None]
        aggregate["review_coverage"] = sum(coverage) / len(coverage) if coverage else None
        return BacktestReport(horizon_days, target, tuple(per_date), aggregate)
