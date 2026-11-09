from contextlib import closing
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from ..core.schemas import MMSValidationError, to_dict


@dataclass(frozen=True)
class ManagerAction:
    sku_id: str
    action: str
    quantity: int | None = None
    note: str = ""


class DecisionRepository:
    def __init__(self, path):
        self.path = str(path)
        if self.path == ":memory:":
            raise MMSValidationError("Use a file-backed SQLite database for durable sessions")
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS decision_sessions (
                    session_id TEXT PRIMARY KEY, analysis_date TEXT NOT NULL,
                    created_at TEXT NOT NULL, result_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decision_items (
                    session_id TEXT NOT NULL REFERENCES decision_sessions(session_id),
                    sku_id TEXT NOT NULL, rank INTEGER NOT NULL, item_json TEXT NOT NULL,
                    action_json TEXT, PRIMARY KEY(session_id, sku_id));
                CREATE TABLE IF NOT EXISTS decision_followups (
                    session_id TEXT NOT NULL, sku_id TEXT NOT NULL,
                    observation_json TEXT NOT NULL, PRIMARY KEY(session_id, sku_id),
                    FOREIGN KEY(session_id, sku_id) REFERENCES decision_items(session_id, sku_id));
            """)

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def save_decision(self, result, actions=()):
        actions = tuple(actions)
        skus = {r.sku_id for r in result.review_list}
        action_map = {}
        for a in actions:
            if a.sku_id not in skus or a.sku_id in action_map or a.action not in {"accepted", "rejected", "edited"}:
                raise MMSValidationError("Unknown/duplicate SKU or unsupported manager action")
            if a.action == "edited" and (type(a.quantity) is not int or a.quantity < 0):
                raise MMSValidationError("Edited quantity must be a nonnegative integer")
            if a.action != "edited" and a.quantity is not None:
                raise MMSValidationError("Only edited actions may specify quantity")
            action_map[a.sku_id] = asdict(a) | {"source": "manager_entered"}
        session_id = str(uuid4())
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO decision_sessions VALUES (?, ?, ?, ?)",
                (session_id, str(result.config.analysis_date), datetime.now(timezone.utc).isoformat(),
                 json.dumps(to_dict(result), allow_nan=False)))
            for item in result.review_list:
                action = action_map.get(item.sku_id)
                db.execute("INSERT INTO decision_items VALUES (?, ?, ?, ?, ?)",
                    (session_id, item.sku_id, item.rank, json.dumps(to_dict(item), allow_nan=False),
                     json.dumps(action) if action else None))
        return self.get_session(session_id)

    def get_session(self, session_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT analysis_date, created_at, result_json FROM decision_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                raise MMSValidationError("Unknown decision session")
            actions = [json.loads(r[0]) for r in db.execute("SELECT action_json FROM decision_items WHERE session_id = ? AND action_json IS NOT NULL ORDER BY rank", (session_id,))]
            followups = [json.loads(r[0]) for r in db.execute("SELECT observation_json FROM decision_followups WHERE session_id = ? ORDER BY sku_id", (session_id,))]
            return dict(session_id=session_id, analysis_date=row[0], created_at=row[1],
                        result=json.loads(row[2]), actions=actions, followups=followups)

    def list_sessions(self):
        with closing(self._connect()) as db:
            return [dict(session_id=r[0], analysis_date=r[1], created_at=r[2]) for r in db.execute(
                "SELECT session_id, analysis_date, created_at FROM decision_sessions ORDER BY created_at DESC, session_id")]

    def add_followups(self, session_id, outcome_provider):
        session = self.get_session(session_id)
        items = session["result"]["review_list"]
        window = outcome_provider.window(session["analysis_date"], [r["sku_id"] for r in items], 30)
        if any(o.sop_day for days in window.values() for o in days):
            raise MMSValidationError("Follow-up window includes SOP days; verified complete observations required")
        with closing(self._connect()) as db, db:
            for sku, days in window.items():
                followup = dict(sku_id=sku, observed_receipt_7d=any(o.received_quantity > 0 for o in days[:7]),
                    observed_stockout_30d=any(o.stockout for o in days), source="inferred_transactions",
                    data_cutoff=str(outcome_provider.data_cutoff), outcome_version=outcome_provider.version)
                db.execute("INSERT INTO decision_followups VALUES (?, ?, ?) ON CONFLICT(session_id, sku_id) DO UPDATE SET observation_json=excluded.observation_json",
                           (session_id, sku, json.dumps(followup)))
        return self.get_session(session_id)
