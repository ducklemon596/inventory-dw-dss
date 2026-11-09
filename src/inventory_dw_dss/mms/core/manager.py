from .directory import list_models
from .schemas import MMSValidationError, ScenarioConfig


class ModelManager:
    def __init__(self):
        self.models = {model.model_id: model for model in list_models()}

    def validate(self, model_id, parameters, analysis_date):
        if model_id not in self.models:
            raise MMSValidationError(f"Unknown model: {model_id}")
        if set(parameters) - set(self.models[model_id].parameters):
            raise MMSValidationError("Unsupported model parameters")
        config = ScenarioConfig(analysis_date=analysis_date, **parameters)
        return self.models[model_id], config
