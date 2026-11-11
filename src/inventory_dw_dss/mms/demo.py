"""Entirely synthetic fixtures, explicitly distinct from trained TN results."""
from datetime import date, timedelta
import json

from .core.schemas import ScenarioConfig, to_dict
from .data.mock import MockDataProvider
from .evaluation.backtesting import Observation, OutcomeProvider
from .service import MMSService


DEMO_DATE = date(2025, 6, 30)


class SyntheticDemoRisk:
    version = "synthetic-demo-v1"
    calibrated = False

    def score(self, rows):
        """Fixed demonstration scores, not HistGB predictions or probabilities."""
        scores = {"A": .9, "B": .8, "C": .8, "D": .1}
        return tuple(scores[r.sku_id] for r in rows)


def build_demo_service():
    inventory, sales = [], []
    for sku, stock, daily_qty, revenue in [("A", 30, 1, 2), ("B", 0, 1, 5),
                                           ("C", 2, 1, 1), ("D", 8, 0, 0)]:
        inventory.append(dict(analysis_date=DEMO_DATE, sku_id=sku, available_stock=stock,
            stock_unit="demo-unit", location_scope="pharmacy_total", snapshot_version="synthetic-snapshot-v1",
            data_version="synthetic-data-v1", feature_as_of=DEMO_DATE, eligible=True, features={}))
        for offset in range(90):
            sales.append(dict(sku_id=sku, sales_date=DEMO_DATE-timedelta(days=offset),
                              quantity=daily_qty, revenue=revenue))
    return MMSService(MockDataProvider(inventory, sales), SyntheticDemoRisk())


def demo_outcomes():
    return OutcomeProvider([Observation(DEMO_DATE+timedelta(days=d), sku,
        sales_quantity=0 if sku == "D" else 2, stockout=(sku == "C" and d == 3),
        received_quantity=5 if d == 2 else 0)
        for sku in "ABCD" for d in range(1, 31)], date(2025, 7, 30), "synthetic-outcomes-v1")


def main():
    result = build_demo_service().execute_scenario(ScenarioConfig(DEMO_DATE, unit_budget_q=15))
    print(json.dumps(to_dict(result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
