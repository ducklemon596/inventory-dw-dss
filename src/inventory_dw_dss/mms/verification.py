"""Verify original bundles and supplied reference cases; never invent TN results."""
import hashlib
import json
import math

from .core.schemas import MMSValidationError, as_date, finite, to_dict
from .evaluation.backtesting import Backtester
from .models.histgb import HistGBRiskModel
from .service import MMSService


def check_artifact(artifact_path, manifest_path):
    model = HistGBRiskModel.load(artifact_path, manifest_path)
    return {"status": "loaded", "artifact_version": model.version,
        "sha256": model.manifest["sha256"], "features": model.manifest["features"],
        "sklearn_version": model.manifest["sklearn_version"],
        "supervised_data_cutoff": model.manifest["supervised_data_cutoff"],
        "compatible_data_versions": model.manifest["compatible_data_versions"],
        "calibrated_declaration": model.calibrated,
        "note": "Bundle contract loaded; golden inference and calibration evidence require original owner inputs"}


def _strict_json(value):
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise MMSValidationError("Reference suite must contain finite JSON values") from exc


def _at_path(value, path):
    try:
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise MMSValidationError(f"Unknown reference output path: {path}") from exc


def _matches(actual, expected, tolerance):
    if type(actual) is bool or type(expected) is bool:
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(actual-expected) <= tolerance
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_matches(actual[k], expected[k], tolerance) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(_matches(a, e, tolerance) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


class _FrozenProvider:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def get_snapshot(self, analysis_date, filters=None):
        return self.snapshots[as_date(analysis_date)]


def run_reference_suite(service, specification, outcome_provider=None):
    canonical = _strict_json(specification)
    if (not isinstance(specification, dict) or specification.get("schema_version") != "mms-reference-v1"
            or not isinstance(specification.get("reference_id"), str) or not specification["reference_id"].strip()
            or not isinstance(specification.get("provenance"), str) or not specification["provenance"].strip()
            or not isinstance(specification.get("cases"), list) or not specification["cases"]):
        raise MMSValidationError("Reference requires schema, identity, provenance and nonempty cases")
    tolerance = finite(specification.get("absolute_tolerance", 1e-8), "absolute_tolerance", 0)
    cases, names = [], set()
    for case in specification["cases"]:
        if not isinstance(case, dict):
            raise MMSValidationError("Each reference case must be an object")
        name, kind = case.get("name"), case.get("kind")
        if not isinstance(name, str) or not name or name in names or kind not in {"scenario", "backtest"}:
            raise MMSValidationError("Reference case requires unique name and scenario/backtest kind")
        names.add(name)
        expected = case.get("expected")
        if not isinstance(expected, dict) or not expected or not all(isinstance(p, str) and p for p in expected):
            raise MMSValidationError("Reference requires nonempty expected output paths")
        try:
            config = service._config(case["config"])
        except (KeyError, TypeError) as exc:
            raise MMSValidationError("Reference requires valid scenario config") from exc
        cohort = case.get("cohort_sku_ids")
        if (not isinstance(cohort, list) or not cohort or not all(isinstance(s, str) and s for s in cohort)
                or len(set(cohort)) != len(cohort)):
            raise MMSValidationError("Reference requires explicit unique cohort SKU IDs")
        versions = case.get("versions")
        if not isinstance(versions, dict) or not {"artifact_version", "data_version", "snapshot_versions"} <= versions.keys():
            raise MMSValidationError("Reference requires artifact/data/snapshot versions")
        if versions["artifact_version"] != getattr(service.executor.risk_model, "version", None):
            raise MMSValidationError("Reference artifact version mismatch")
        if kind == "scenario":
            dates = [config.analysis_date]
        else:
            raw_dates = case.get("decision_dates")
            if not isinstance(raw_dates, list) or not raw_dates:
                raise MMSValidationError("Backtest reference requires decision_dates")
            dates = sorted({as_date(d) for d in raw_dates})
        snapshots = {}
        for t in dates:
            snapshot = service.provider.get_snapshot(t, {"sku_ids": cohort})
            if sorted(r.sku_id for r in snapshot.rows) != sorted(cohort):
                raise MMSValidationError("Reference cohort differs from available snapshot")
            if snapshot.analysis_date != t or snapshot.data_version != versions["data_version"]:
                raise MMSValidationError("Reference analysis date or data version mismatch")
            if not isinstance(versions["snapshot_versions"], dict) or versions["snapshot_versions"].get(str(t)) != snapshot.snapshot_version:
                raise MMSValidationError("Reference snapshot version mismatch")
            snapshots[t] = snapshot
        frozen = MMSService(_FrozenProvider(snapshots), service.executor.risk_model)
        if kind == "scenario":
            result = frozen.execute_scenario(config)
            actual = {"review_skus": [r.sku_id for r in result.review_list],
                "order_units": {r.sku_id: r.allocated_q for r in result.order_proposal},
                "suggested_units": {r.sku_id: r.suggested_q for r in result.review_list},
                "summary": result.summary, "metadata": result.metadata}
        else:
            if outcome_provider is None or versions.get("outcome_version") != outcome_provider.version:
                raise MMSValidationError("Backtest requires matching outcome provider/version")
            if "horizon_days" not in case:
                raise MMSValidationError("Backtest reference requires horizon_days")
            actual = to_dict(Backtester(frozen, outcome_provider).run(config, dates, case["horizon_days"]))
        differences = []
        for path, wanted in expected.items():
            observed = _at_path(actual, path)
            if not _matches(observed, wanted, tolerance):
                differences.append({"path": path, "expected": wanted, "actual": observed})
        cases.append({"name": name, "kind": kind, "status": "failed" if differences else "passed",
                      "versions": versions, "cohort_size": len(cohort), "differences": differences})
    return {"reference_id": specification["reference_id"], "provenance": specification["provenance"],
        "reference_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "absolute_tolerance": tolerance, "passed": all(c["status"] == "passed" for c in cases),
        "cases": cases, "observational_only": True}
