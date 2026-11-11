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


POLICY_PARAMETERS = ("coverage_tau_days", "policy", "service_level", "lead_time_days", "abc_service")


def list_models():
    return [
        ModelMetadata("MB1", "MA90", "ma90-v1", "Sales-based demand proxy; not fulfilled/lost demand.",
                      ("sales_90d",), (), ("vel90", "forecast_30d"), "models.ma90.forecast"),
        ModelMetadata("MB2", "HistGB stockout risk", "manifest-required", "Requires verified trained artifact; score calibration declared in manifest.",
                      ("manifest.features",), (), ("risk_score",), "models.histgb.HistGBRiskModel.score"),
        ModelMetadata("MB3", "Replenishment policy", "coverage-mvp-v1|service-level-nb-v1",
                      "coverage: ceil(tau x MA90 - stock). service_level: order up to the negative-binomial demand "
                      "quantile over review + lead time.",
                      ("available_stock", "vel90", "eligible", "sales_std_90d", "abc_class"), POLICY_PARAMETERS,
                      ("suggested_q", "target_level", "safety_stock", "service_level"), "models.policy.propose"),
        ModelMetadata("MB4", "Scenario allocation", "scenario-mvp-v1", "Provisional deterministic greedy partial unit allocation; no optimality claim.",
                      ("MB1", "MB2", "MB3"), ("profile", "pstar", "top_k", "unit_budget_q") + POLICY_PARAMETERS,
                      ("review_list", "order_proposal", "summary"), "models.scenario.execute"),
    ]
