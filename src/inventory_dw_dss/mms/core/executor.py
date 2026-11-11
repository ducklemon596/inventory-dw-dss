from .directory import list_models
from .manager import ModelManager
from .schemas import ArtifactError, ExecutionError, MMSValidationError, ModelResult, to_dict
from ..models.ma90 import forecast
from ..models.replenishment import suggested_quantity


class ModelExecutor:
    def __init__(self, risk_model=None):
        self.risk_model = risk_model
        self.manager = ModelManager()

    def list_models(self):
        return list_models()

    def risk_scores(self, snapshot):
        if self.risk_model is None:
            raise ArtifactError("HistGB artifact is unavailable; configure an approved artifact and manifest")
        if hasattr(self.risk_model, "validate_snapshot"):
            self.risk_model.validate_snapshot(snapshot)
        scores = tuple(self.risk_model.score(snapshot.rows))
        from .schemas import finite
        if len(scores) != len(snapshot.rows) or any(not 0 <= finite(s, "risk_score") <= 1 for s in scores):
            raise ArtifactError("Risk scorer returned invalid scores")
        return scores

    def run_model(self, model_id, snapshot, parameters=None):
        metadata = {"analysis_date": str(snapshot.analysis_date), "snapshot_version": snapshot.snapshot_version,
                    "data_version": snapshot.data_version, "location_scope": snapshot.location_scope,
                    "artifact_version": getattr(self.risk_model, "version", None),
                    "supervised_data_cutoff": getattr(self.risk_model, "manifest", {}).get("supervised_data_cutoff"),
                    "calibrated": getattr(self.risk_model, "calibrated", False)}
        try:
            model, config = self.manager.validate(model_id, parameters or {}, snapshot.analysis_date)
            metadata["model_version"] = model.version
            metadata["parameters"] = dict(parameters or {})
            if model_id == "MB1":
                items = tuple({"sku_id": r.sku_id, **forecast(r)} for r in snapshot.rows)
            elif model_id == "MB2":
                scores = self.risk_scores(snapshot)
                items = tuple({"sku_id": r.sku_id, "risk_score": score} for r, score in zip(snapshot.rows, scores))
            elif model_id == "MB3":
                items = tuple({"sku_id": r.sku_id, "suggested_q": suggested_quantity(r, config.coverage_tau_days)} for r in snapshot.rows)
            else:
                from ..models.scenario import execute
                result = execute(snapshot, config, self.risk_scores(snapshot), metadata)
                items = (to_dict(result),)
            return ModelResult(model_id, True, items, metadata)
        except (MMSValidationError, TypeError) as exc:
            code = "artifact_unavailable" if isinstance(exc, ArtifactError) else "invalid_request"
            return ModelResult(model_id, False, (), metadata, ExecutionError(code, str(exc)))
