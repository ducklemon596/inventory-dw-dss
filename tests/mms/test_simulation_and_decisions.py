from datetime import timedelta

import numpy as np
import pytest

from inventory_dw_dss.mms.decisions import Decision, DecisionStore
from inventory_dw_dss.mms.evaluation.policy_simulation import SimulationData, parse_policy, simulate
from inventory_dw_dss.mms.models.scenario import build_plan
from inventory_dw_dss.mms.schemas import InventorySnapshot, MMSError, ScenarioConfig

from fixtures import T, VERSION, row


def two_products():
    """X sells one unit a day from an empty start; Y has no demand. Reviews on days 0 and 7."""
    days = tuple(T + timedelta(days=i) for i in range(14))
    reviews = (days[0], days[7])
    return SimulationData(days, (1, 2), np.tile([1., 0.], (14, 1)), np.zeros((14, 2)), np.array([10., 10.]),
                          {d: np.array([1., 0.]) for d in reviews}, {d: np.array([np.nan, np.nan]) for d in reviews},
                          {d: np.array(["A", None], dtype=object) for d in reviews})


def test_simulation_replays_orders_by_hand():
    data = two_products()
    result = simulate(data, parse_policy("coverage:7"), review_days=7, lead_time_days=0)
    # 7 units arrive each Monday and sell out on the 7th day.
    assert result["fill_rate"] == 1 and result["units_ordered"] == 14 and result["stockout_day_share"] == 2 / 14
    assert result["avg_inventory_value"] == 2 * (6 + 5 + 4 + 3 + 2 + 1) * 10 / 14
    late = simulate(data, parse_policy("coverage:7"), 7, 2)
    service = simulate(data, parse_policy("service:0.95"), 7, 2)
    # Both lose the first two days to the empty start; covering review + lead time avoids later gaps.
    assert late["fill_rate"] == service["fill_rate"] == 12 / 14
    assert service["stockout_day_share"] < late["stockout_day_share"]
    with pytest.raises(MMSError):
        parse_policy("service:1.2")


def test_decisions_round_trip_and_validation(tmp_path):
    plan = build_plan(InventorySnapshot(T, VERSION, (row("A", 0), row("B", 1))), ScenarioConfig(T, pstar=0),
                      (.9, .8))
    store = DecisionStore(tmp_path / "decisions.sqlite")
    session = store.save(plan, [Decision("A", "approved", 10, "supplier promo"), Decision("B", "rejected")])
    assert store.sessions()[0] == {"session_id": session, "analysis_date": str(T),
                                   "created_at": store.sessions()[0]["created_at"], "approved": 1}
    saved, decisions = store.load(session)
    assert saved["items"][0]["sku_id"] == "A" and decisions["A"].quantity == 10 and decisions["B"].quantity is None
    with pytest.raises(MMSError):
        store.save(plan, [Decision("A", "approved", -1)])
    with pytest.raises(MMSError):
        store.save(plan, [Decision("Z", "approved", 1)])
