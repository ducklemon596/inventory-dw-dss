from dataclasses import dataclass, replace
from datetime import date, timedelta

from ..core.schemas import MMSValidationError, as_date, finite, to_dict
from ..models.scenario import execute
from .metrics import demand_metrics, risk_metrics


@dataclass(frozen=True)
class Observation:
    observation_date: date
    sku_id: str
    sales_quantity: float
    stockout: bool
    received_quantity: float = 0
    sop_day: bool = False

    def __post_init__(self):
        object.__setattr__(self, "observation_date", as_date(self.observation_date))
        finite(self.sales_quantity, "observed sales", 0)
        finite(self.received_quantity, "observed receipts", 0)
        if not self.sku_id or type(self.stockout) is not bool or type(self.sop_day) is not bool:
            raise MMSValidationError("Observed labels must be explicit boolean pharmacy-total observations")


class OutcomeProvider:
    def __init__(self, observations, data_cutoff, version):
        self.observations = tuple(observations)
        self.data_cutoff = as_date(data_cutoff)
        self.version = version
        keys = [(o.sku_id, o.observation_date) for o in self.observations]
        if len(set(keys)) != len(keys) or not version:
            raise MMSValidationError("Duplicate outcomes or missing outcome version")
        self._index = {(o.sku_id, o.observation_date): o for o in self.observations}

    def window(self, t, sku_ids, horizon):
        t = as_date(t)
        if self.data_cutoff < t + timedelta(days=horizon):
            raise MMSValidationError("Observation window is not complete at the data cutoff")
        result = {}
        for sku in sku_ids:
            days = []
            for offset in range(1, horizon+1):
                o = self._index.get((sku, t+timedelta(days=offset)))
                if o is None:
                    raise MMSValidationError(f"Observation window is not complete for {sku}")
                days.append(o)
            result[sku] = tuple(days)
        return result

    @classmethod
    def from_duckdb(cls, connection):
        """Optional outcome export with one explicit metadata row and daily labels."""
        import duckdb
        try:
            metadata = connection.execute("SELECT data_cutoff, outcome_version FROM mms_outcome_metadata").fetchall()
            if len(metadata) != 1:
                raise MMSValidationError("Expected one outcome metadata row")
            cursor = connection.execute("SELECT observation_date, sku_id, sales_quantity, stockout, received_quantity, sop_day FROM mms_outcomes_daily")
            return cls([Observation(*row) for row in cursor.fetchall()], *metadata[0])
        except duckdb.Error as exc:
            raise MMSValidationError(f"Cannot read optional outcome export: {exc}") from exc


@dataclass(frozen=True)
class BacktestReport:
    config: dict
    horizon_days: int
    per_date: tuple[dict, ...]
    aggregate: dict


class Backtester:
    def __init__(self, service, outcome_provider):
        self.service = service
        self.outcomes = outcome_provider

    def run(self, config, decision_dates, horizon_days=30):
        if horizon_days not in (7, 14, 30) or type(horizon_days) is not int:
            raise MMSValidationError("Evaluation horizon must be 7, 14 or 30 days")
        config = self.service._config(config)
        dates = sorted({as_date(t) for t in decision_dates})
        if not dates:
            raise MMSValidationError("At least one decision date is required")
        per_date = []
        for t in dates:
            row = {"analysis_date": str(t)}
            if t == date(2025, 7, 31) and horizon_days == 30:
                per_date.append(dict(row, status="excluded_sop202508"))
                continue
            snapshot = self.service.provider.get_snapshot(t)
            if snapshot.analysis_date != t:
                raise MMSValidationError("Provider returned a different analysis date")
            try:
                future = self.outcomes.window(t, [r.sku_id for r in snapshot.rows], horizon_days)
            except MMSValidationError as exc:
                per_date.append(dict(row, status="incomplete", reason=str(exc)))
                continue
            if any(o.sop_day for days in future.values() for o in days):
                per_date.append(dict(row, status="excluded_sop"))
                continue
            scores = self.service.executor.risk_scores(snapshot)
            metadata = self.service._metadata(snapshot) | {"outcome_version": self.outcomes.version,
                "outcome_data_cutoff": str(self.outcomes.data_cutoff),
                "outcome_start": str(t+timedelta(days=1)), "outcome_end": str(t+timedelta(days=horizon_days))}
            result = execute(snapshot, replace(config, analysis_date=t), scores, metadata)
            # Incident-stockout ranking metrics exclude existing zero/negative balances.
            cohort = [(r, score) for r, score in zip(snapshot.rows, scores) if r.available_stock > 0]
            labels = [int(any(o.stockout for o in future[r.sku_id])) for r, _ in cohort]
            risk = risk_metrics(labels, [s for _, s in cohort], [r.sku_id for r, _ in cohort], config.top_k)
            actual = [sum(o.sales_quantity for o in future[r.sku_id]) for r in snapshot.rows]
            predicted = [r.vel90*horizon_days for r in snapshot.rows]
            review_skus = {item.sku_id for item in result.review_list}
            new_stockout_skus = {r.sku_id for (r, _), label in zip(cohort, labels) if label}
            quantities = [item.suggested_q for item in result.review_list]
            allocation = dict(result.summary, quantity_distribution={
                "min": min(quantities) if quantities else None, "max": max(quantities) if quantities else None,
                "mean": sum(quantities)/len(quantities) if quantities else None},
                q_zero_frequency=result.summary["q_zero_count"]/len(quantities) if quantities else None,
                stockout_coverage=len(review_skus & new_stockout_skus)/len(new_stockout_skus) if new_stockout_skus else None)
            per_date.append(dict(row, status="evaluated", metadata=metadata,
                demand=demand_metrics(actual, predicted), risk=risk, allocation=allocation,
                existing_stockout_count=sum(r.available_stock == 0 for r in snapshot.rows),
                negative_balance_count=sum(r.available_stock < 0 for r in snapshot.rows),
                new_stockout_count=sum(labels)))
        evaluated = [r for r in per_date if r["status"] == "evaluated"]
        aggregate = {"evaluated_dates": len(evaluated), "excluded_or_incomplete_dates": len(per_date)-len(evaluated),
                     "aggregation": "macro average across evaluated dates, excluding undefined metrics"}
        for group in ("demand", "risk"):
            keys = ("wape", "bias") if group == "demand" else ("precision_at_k", "recall_at_k", "lift", "roc_auc")
            aggregate[group] = {}
            for key in keys:
                values = [r[group][key] for r in evaluated if r[group][key] is not None]
                aggregate[group][key] = sum(values)/len(values) if values else None
        return BacktestReport(to_dict(config), horizon_days, tuple(per_date), aggregate)
