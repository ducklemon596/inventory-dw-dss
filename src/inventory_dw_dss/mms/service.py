"""MMS entry point shared by the CLI and the Streamlit app.

Configuration comes from the environment:
    MMS_ARTIFACT_PATH, MMS_MANIFEST_PATH   trained risk model bundle
    MMS_DECISIONS_PATH                     SQLite file for saved decisions (app only)
    CLICKHOUSE_HOST / _HTTP_PORT / _DB / _USER / _PASSWORD / _SECURE
"""
import os

from .data import MartReader
from .models.risk import RiskModel
from .models.scenario import build_plan
from .schemas import MMSError


class MMSService:
    def __init__(self, reader, risk_model):
        self.reader = reader
        self.risk_model = risk_model

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        artifact, manifest = env.get("MMS_ARTIFACT_PATH"), env.get("MMS_MANIFEST_PATH")
        if not artifact or not manifest:
            raise MMSError("Set MMS_ARTIFACT_PATH and MMS_MANIFEST_PATH to a trained risk model "
                           "(inventory-mms train)")
        return cls(MartReader(), RiskModel.load(artifact, manifest))

    def scores(self, snapshot):
        self.risk_model.check_snapshot(snapshot)
        return self.risk_model.score(snapshot.rows)

    def _metadata(self, snapshot):
        return {"analysis_date": str(snapshot.analysis_date), "data_version": snapshot.data_version,
                "risk_model": self.risk_model.version, "risk_target": self.risk_model.target,
                "risk_horizon_days": self.risk_model.horizon_days}

    def plan(self, config):
        return self.compare([config])[0]

    def compare(self, configs):
        """Plans for several configurations on one snapshot and one set of risk scores."""
        if len({c.analysis_date for c in configs}) != 1:
            raise MMSError("Compared plans must share an analysis date")
        snapshot = self.reader.snapshot(configs[0].analysis_date)
        scores = self.scores(snapshot)
        return [build_plan(snapshot, c, scores, self._metadata(snapshot)) for c in configs]
