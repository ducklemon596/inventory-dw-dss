from dataclasses import dataclass


@dataclass(frozen=True)
class ModelMetadata:
    model_id: str
    name: str
    version: str
    description: str
    required_inputs: tuple[str, ...]
    parameters: tuple[str, ...]
    outputs: tuple[str, ...]
    callable_reference: str


def list_models():
    return [
        ModelMetadata("MB1", "MA90", "ma90-v1", "Sales-based demand proxy; not fulfilled/lost demand.",
                      ("sales_90d",), (), ("vel90", "forecast_30d"), "models.ma90.forecast"),
        ModelMetadata("MB2", "HistGB stockout risk", "manifest-required", "Requires verified trained artifact; score calibration declared in manifest.",
                      ("manifest.features",), (), ("risk_score",), "models.histgb.HistGBRiskModel.score"),
        ModelMetadata("MB3", "Coverage replenishment", "coverage-mvp-v1", "Provisional ceil rule pending TN verification.",
                      ("available_stock", "vel90", "eligible"), ("coverage_tau_days",), ("suggested_q",), "models.replenishment.suggested_quantity"),
        ModelMetadata("MB4", "Scenario allocation", "scenario-mvp-v1", "Provisional deterministic greedy partial unit allocation; no optimality claim.",
                      ("MB1", "MB2", "MB3"), ("profile", "pstar", "top_k", "unit_budget_q", "coverage_tau_days"),
                      ("review_list", "order_proposal", "summary"), "models.scenario.execute"),
    ]
