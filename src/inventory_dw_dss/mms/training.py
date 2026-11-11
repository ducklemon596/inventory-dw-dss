"""New, explicitly versioned HistGB training; not a reconstruction of absent TN code."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from .core.schemas import MMSValidationError, as_date


FEATURES = ("available_stock", "sales_7d", "sales_30d", "vel90")
BASIC_PARAMS = {"max_iter": 60, "max_leaf_nodes": 7, "min_samples_leaf": 10, "l2_regularization": 1.,
                "early_stopping": False}

# Selected on 2023-2025 pharmacy backtests (temporal train/validation/test split); see
# docs/mms-real-data-evaluation.md. Missing values (e.g. no sales yet) use HistGB's native branch.
MART_CANONICAL = ("available_stock", "sales_7d", "sales_30d", "sales_90d", "vel90", "dos", "revenue_90d",
                  "days_since_last_receipt")
MART_PARAMS = {"max_iter": 300, "learning_rate": .05, "max_leaf_nodes": 31, "min_samples_leaf": 50,
               "l2_regularization": 1., "early_stopping": False}


def feature_set(name):
    """Named training configurations: (features, model parameters, native missing values, SOP scope)."""
    if name == "basic":
        return FEATURES, BASIC_PARAMS, False, "date"
    if name == "mart":
        from .data.mart_adapter import MART_FEATURES
        return MART_CANONICAL + MART_FEATURES, MART_PARAMS, True, "sku"
    raise MMSValidationError("Feature set must be basic or mart")


def train_histgb(provider, outcomes, decision_dates, output_directory, artifact_version, *, data_kind,
                 horizon_days=7, seed=7, features_name="basic", sop_scope=None,
                 risk_target="dispensary_stockout"):
    import joblib
    import pandas as pd
    import sklearn
    from sklearn.ensemble import HistGradientBoostingClassifier
    from .models.histgb import feature_matrix
    from .models.targets import LABEL_DEFINITIONS, check_target, target_label, target_stock

    target = Path(output_directory).resolve()
    if target.exists():
        raise MMSValidationError("Artifact output directory already exists; use a new immutable version path")
    if data_kind not in {"synthetic", "verified"} or not isinstance(artifact_version, str) or not artifact_version:
        raise MMSValidationError("Training requires data_kind synthetic/verified and an artifact version")
    if (type(horizon_days) is not int or horizon_days not in {7, 14, 30}
            or type(seed) is not int or not 0 <= seed <= 2**32-1):
        raise MMSValidationError("Training requires a 7/14/30-day horizon and integer seed in [0,2**32-1]")
    check_target(risk_target)
    features, params, allow_missing, default_scope = feature_set(features_name)
    sop_scope = sop_scope or default_scope
    if sop_scope not in ("date", "sku"):
        raise MMSValidationError("sop_scope must be date or sku")
    dates = sorted({as_date(t) for t in decision_dates})
    if not dates:
        raise MMSValidationError("Training dates are required")
    examples, versions, included, excluded = [], set(), [], []
    sop_rows = 0
    for t in dates:
        snapshot = provider.get_snapshot(t)
        if snapshot.analysis_date != t:
            raise MMSValidationError("Training provider returned a different date")
        # Incident cohort: eligible products still holding the stock the target measures.
        cohort = [r for r in snapshot.rows if target_stock(r, risk_target) > 0 and r.eligible]
        future = outcomes.window(t, [r.sku_id for r in cohort], horizon_days)
        if sop_scope == "date" and any(o.sop_day for days in future.values() for o in days):
            excluded.append({"analysis_date": str(t), "reason": "SOP outcome window"})
            continue
        versions.add(snapshot.data_version)
        included.append(t)
        # Per-SKU scope suits daily cycle counts: only windows touched by a stocktake are dropped.
        if sop_scope == "sku":
            kept = [r for r in cohort if not any(o.sop_day for o in future[r.sku_id])]
            sop_rows += len(cohort) - len(kept)
            cohort = kept
        for row, vector in zip(cohort, feature_matrix(cohort, features, allow_missing)):
            examples.append({"date": str(t), "sku_id": row.sku_id,
                             "features": [None if v != v else v for v in vector],
                             "label": target_label(row, future[row.sku_id], risk_target)})
    if len(versions) != 1:
        raise MMSValidationError("Training requires one consistent data version")
    if data_kind == "verified" and any(v.startswith("synthetic") for v in versions):
        raise MMSValidationError("Synthetic data cannot be declared verified production data")
    if len(examples) < 20 or {e["label"] for e in examples} != {0, 1}:
        raise MMSValidationError("Training needs at least 20 eligible samples and both outcome classes")
    training_hash = hashlib.sha256(json.dumps({"examples": examples, "features": features,
        "horizon_days": horizon_days, "seed": seed, "outcome_version": outcomes.version,
        **({"risk_target": risk_target} if risk_target != "dispensary_stockout" else {})},
        sort_keys=True, allow_nan=False).encode()).hexdigest()
    x = pd.DataFrame([e["features"] for e in examples], columns=list(features), dtype=float)
    model = HistGradientBoostingClassifier(random_state=seed, **params)
    model.fit(x, [e["label"] for e in examples])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mms-training-", dir=target.parent) as temporary:
        staged = Path(temporary)/"bundle"
        staged.mkdir()
        artifact = staged/"histgb.joblib"
        joblib.dump(model, artifact)
        manifest = {"artifact_version": artifact_version, "sklearn_version": sklearn.__version__,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "features": list(features),
            "positive_class": 1, "preprocessing": "embedded", "calibrated": False,
            "compatible_data_versions": sorted(versions),
            "supervised_data_cutoff": str(max(included)+timedelta(days=horizon_days)),
            "training_dates": [str(t) for t in included], "excluded_dates": excluded,
            "training_samples": len(examples), "positive_samples": sum(e["label"] for e in examples),
            "training_data_sha256": training_hash, "outcome_version": outcomes.version,
            "label_horizon_days": horizon_days, "random_seed": seed, "data_kind": data_kind,
            "feature_set": features_name, "model_params": params, "sop_scope": sop_scope,
            "excluded_sop_rows": sop_rows, **({"missing_values": "native"} if allow_missing else {}),
            "risk_target": risk_target, "label_definition": LABEL_DEFINITIONS[risk_target],
            "training_protocol": "new-histgb-v1; fixed parameters; no held-out tuning or calibration",
            "original_tn_reproduction": False}
        (staged/"manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        staged.rename(target)
    return {"artifact": str(target/"histgb.joblib"), "manifest": str(target/"manifest.json"),
            "training_samples": len(examples), "supervised_data_cutoff": manifest["supervised_data_cutoff"],
            "data_kind": data_kind, "original_tn_reproduction": False}


def build_synthetic_bundle(output_directory, seed=7):
    from .synthetic import build_bundle
    return build_bundle(output_directory, seed)
