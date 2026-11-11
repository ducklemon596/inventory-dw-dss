from copy import deepcopy

import pytest

from inventory_dw_dss.mms.core.schemas import MMSValidationError
from inventory_dw_dss.mms.demo import build_demo_service, demo_outcomes
from inventory_dw_dss.mms.verification import run_reference_suite, check_artifact


def reference():
    return dict(schema_version="mms-reference-v1", reference_id="synthetic-test-only",
        provenance="Synthetic fixture; not original TN results", cases=[dict(
            name="budget-example", kind="scenario", config={"analysis_date": "2025-06-30", "unit_budget_q": 15},
            cohort_sku_ids=list("ABCD"), versions=dict(artifact_version="synthetic-demo-v1",
                data_version="synthetic-data-v1", snapshot_versions={"2025-06-30": "synthetic-snapshot-v1"}),
            expected={"review_skus": ["A", "B", "C"], "order_units": {"B": 14, "C": 1},
                      "summary.units_allocated": 15})])


def test_reference_scenarios_compare_exact_cohort_versions_and_quantities():
    spec = reference()
    report = run_reference_suite(build_demo_service(), spec)
    assert report["passed"] and report["reference_id"] == spec["reference_id"]
    assert report["cases"][0]["status"] == "passed"
    spec["cases"][0]["expected"]["order_units"]["C"] = 2
    report = run_reference_suite(build_demo_service(), spec)
    assert not report["passed"]
    assert report["cases"][0]["differences"][0]["path"] == "order_units"


@pytest.mark.parametrize("fault", ["empty_cases", "empty_expected", "unknown_path", "wrong_version",
    "wrong_cohort", "nan", "negative_tolerance", "missing_provenance", "unknown_kind"])
def test_reference_contract_rejects_vacuous_or_mismatched_comparisons(fault):
    spec = reference()
    case = spec["cases"][0]
    if fault == "empty_cases": spec["cases"] = []
    if fault == "empty_expected": case["expected"] = {}
    if fault == "unknown_path": case["expected"]["invented.metric"] = 1
    if fault == "wrong_version": case["versions"]["artifact_version"] = "unrelated-model"
    if fault == "wrong_cohort": case["cohort_sku_ids"] = ["missing"]
    if fault == "nan": case["expected"]["summary.units_allocated"] = float("nan")
    if fault == "negative_tolerance": spec["absolute_tolerance"] = -1
    if fault == "missing_provenance": spec["provenance"] = ""
    if fault == "unknown_kind": case["kind"] = "train"
    with pytest.raises(MMSValidationError): run_reference_suite(build_demo_service(), spec)


def test_backtest_reference_uses_matching_horizon_and_outcome_version():
    spec = reference()
    case = spec["cases"][0]
    case.update(kind="backtest", decision_dates=["2025-06-30"], horizon_days=7,
        expected={"aggregate.evaluated_dates": 1, "per_date.0.status": "evaluated",
                  "per_date.0.demand.wape": .5})
    case["versions"]["outcome_version"] = "synthetic-outcomes-v1"
    assert run_reference_suite(build_demo_service(), spec, demo_outcomes())["passed"]
    case["versions"]["outcome_version"] = "wrong"
    with pytest.raises(MMSValidationError): run_reference_suite(build_demo_service(), spec, demo_outcomes())


def test_artifact_checker_reports_missing_bundle_without_training(tmp_path):
    from inventory_dw_dss.mms.core.schemas import ArtifactError
    with pytest.raises(ArtifactError): check_artifact(tmp_path/"missing.joblib", tmp_path/"missing.json")
