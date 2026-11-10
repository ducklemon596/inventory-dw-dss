from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest

from inventory_dw_dss.mms.core.schemas import MMSValidationError, ScenarioConfig, to_dict
from inventory_dw_dss.mms.tracking.repository import DecisionRepository, ManagerAction
from test_scenarios import service
from test_backtesting import outcomes
from test_data import T


def test_save_reopen_exact_config_versions_and_manager_actions(tmp_path):
    path = tmp_path / "decisions.sqlite"
    repo = DecisionRepository(path)
    result = service().execute_scenario(ScenarioConfig(T, unit_budget_q=5))
    session = repo.save_decision(result, [ManagerAction("B", "edited", quantity=3, note="Supplier constraint")])
    loaded = DecisionRepository(path).get_session(session["session_id"])
    assert loaded["result"] == to_dict(result)
    assert loaded["actions"][0]["source"] == "manager_entered"
    assert loaded["actions"][0]["quantity"] == 3
    assert loaded["actions"][0]["note"] == "Supplier constraint"
    assert repo.list_sessions()[0]["session_id"] == session["session_id"]
    assert not loaded["followups"]


def test_tracking_rejects_unknown_actions_and_invalid_edits_atomically(tmp_path):
    repo = DecisionRepository(tmp_path / "decisions.sqlite")
    result = service().execute_scenario(ScenarioConfig(T))
    for actions in ([ManagerAction("unknown", "accepted")], [ManagerAction("B", "edited", quantity=-1)],
                    [ManagerAction("B", "edited")], [ManagerAction("B", "unknown")],
                    [ManagerAction("B", "accepted")]*2):
        with pytest.raises(MMSValidationError): repo.save_decision(result, actions)
    assert repo.list_sessions() == []


def test_followup_requires_full_observations_and_keeps_sources_separate(tmp_path):
    repo = DecisionRepository(tmp_path / "decisions.sqlite")
    result = service().execute_scenario(ScenarioConfig(T))
    session_id = repo.save_decision(result, [ManagerAction("B", "rejected", note="Review later")])["session_id"]
    with pytest.raises(MMSValidationError, match="complete"):
        repo.add_followups(session_id, outcomes(horizon=7))
    repo.add_followups(session_id, outcomes())
    loaded = repo.get_session(session_id)
    assert len(loaded["followups"]) == 3
    assert loaded["followups"][0]["source"] == "inferred_transactions"
    assert loaded["followups"][0]["observed_receipt_7d"] is True
    assert next(f for f in loaded["followups"] if f["sku_id"] == "C")["observed_stockout_30d"] is True
    assert loaded["actions"][0]["action"] == "rejected"
    repo.add_followups(session_id, outcomes())
    assert len(repo.get_session(session_id)["followups"]) == 3


def test_pending_manager_note_is_saved_without_approving_order(tmp_path):
    repo=DecisionRepository(tmp_path/"notes.sqlite")
    result=service().execute_scenario(ScenarioConfig(T))
    saved=repo.save_decision(result,[ManagerAction("B","pending",note="Kiểm tra tồn thực tế")])
    assert saved["actions"][0]["action"] == "pending"
    assert saved["actions"][0]["note"] == "Kiểm tra tồn thực tế"
    assert saved["actions"][0]["quantity"] is None
