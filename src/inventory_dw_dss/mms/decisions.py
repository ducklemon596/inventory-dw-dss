"""Saved manager decisions in a local SQLite file.

A session stores the full plan (configuration, items, metadata) and one decision per line:
approved with a quantity, rejected, or still pending, plus a free-text note.
"""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from .schemas import MMSError, to_dict

STATUSES = ("pending", "approved", "rejected")


@dataclass(frozen=True)
class Decision:
    sku_id: str
    status: str = "pending"
    quantity: int | None = None   # approved quantity; may differ from the suggestion
    note: str = ""


class DecisionStore:
    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    analysis_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    sku_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity INTEGER,
                    note TEXT NOT NULL,
                    PRIMARY KEY (session_id, sku_id));
            """)

    def save(self, plan, decisions):
        skus = {i.sku_id for i in plan.items}
        for d in decisions:
            if d.sku_id not in skus or d.status not in STATUSES:
                raise MMSError(f"Invalid decision for {d.sku_id}")
            if d.status == "approved" and (type(d.quantity) is not int or d.quantity < 0):
                raise MMSError(f"Approved quantity for {d.sku_id} must be a nonnegative integer")
        session_id = str(uuid4())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (session_id, str(plan.config.analysis_date), datetime.now(timezone.utc).isoformat(),
                        json.dumps(to_dict(plan), ensure_ascii=False)))
            db.executemany("INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
                           [(session_id, d.sku_id, d.status, d.quantity if d.status == "approved" else None, d.note)
                            for d in decisions])
        return session_id

    def sessions(self):
        """Newest first: id, analysis date, creation time and approved line count."""
        with closing(sqlite3.connect(self.path)) as db:
            return [dict(session_id=r[0], analysis_date=r[1], created_at=r[2], approved=r[3]) for r in db.execute(
                "SELECT s.session_id, s.analysis_date, s.created_at, count(d.sku_id) FILTER (WHERE d.status = 'approved') "
                "FROM sessions s LEFT JOIN decisions d USING (session_id) "
                "GROUP BY s.session_id ORDER BY s.created_at DESC")]

    def load(self, session_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT plan_json FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                raise MMSError("Unknown decision session")
            decisions = {r[0]: Decision(*r) for r in db.execute(
                "SELECT sku_id, status, quantity, note FROM decisions WHERE session_id = ?", (session_id,))}
        return json.loads(row[0]), decisions
