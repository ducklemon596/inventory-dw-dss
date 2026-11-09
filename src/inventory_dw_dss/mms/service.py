"""Single UI boundary: model logic stays outside Streamlit."""
from .core.executor import ModelExecutor
from .core.schemas import MMSValidationError, ScenarioComparison, ScenarioConfig
from .evaluation.scenario_comparison import compare_results
from .models.scenario import execute


class MMSService:
    def __init__(self, provider, risk_model=None):
        self.provider = provider
        self.executor = ModelExecutor(risk_model)

    def list_models(self):
        return self.executor.list_models()

    def run_model(self, model_id, snapshot, parameters=None):
        return self.executor.run_model(model_id, snapshot, parameters)

    @staticmethod
    def _config(config):
        return config if isinstance(config, ScenarioConfig) else ScenarioConfig(**config)

    def _metadata(self, snapshot):
        return {"analysis_date": str(snapshot.analysis_date), "snapshot_version": snapshot.snapshot_version,
                "data_version": snapshot.data_version, "location_scope": snapshot.location_scope,
                "artifact_version": self.executor.risk_model.version,
                "supervised_data_cutoff": getattr(self.executor.risk_model, "manifest", {}).get("supervised_data_cutoff"),
                "calibrated": self.executor.risk_model.calibrated,
                "model_versions": {m.model_id: m.version for m in self.list_models()}}

    def execute_scenario(self, config):
        config = self._config(config)
        snapshot = self.provider.get_snapshot(config.analysis_date)
        scores = self.executor.risk_scores(snapshot)
        return execute(snapshot, config, scores, self._metadata(snapshot))

    def compare_scenarios(self, configs):
        configs = tuple(self._config(c) for c in configs)
        if not 2 <= len(configs) <= 4:
            raise MMSValidationError("Compare requires 2–4 scenarios")
        if len({c.analysis_date for c in configs}) != 1:
            raise MMSValidationError("Compared scenarios must use the same analysis date")
        snapshot = self.provider.get_snapshot(configs[0].analysis_date)
        scores = self.executor.risk_scores(snapshot)
        metadata = self._metadata(snapshot)
        results = tuple(execute(snapshot, c, scores, metadata) for c in configs)
        return ScenarioComparison(results, compare_results(results))
