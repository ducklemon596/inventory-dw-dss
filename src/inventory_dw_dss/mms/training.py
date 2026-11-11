"""New, explicitly versioned HistGB training; not a reconstruction of absent TN code."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from .core.schemas import MMSValidationError, as_date, finite


FEATURES = ("available_stock", "sales_7d", "sales_30d", "vel90")


def train_histgb(provider, outcomes, decision_dates, output_directory, artifact_version, *, data_kind,
                 horizon_days=7, seed=7):
    import joblib
    import pandas as pd
    import sklearn
    from sklearn.ensemble import HistGradientBoostingClassifier

    target = Path(output_directory).resolve()
    if target.exists():
        raise MMSValidationError("Artifact output directory already exists; use a new immutable version path")
    if data_kind not in {"synthetic", "verified"} or not isinstance(artifact_version, str) or not artifact_version:
        raise MMSValidationError("Training requires data_kind synthetic/verified and an artifact version")
    if (type(horizon_days) is not int or horizon_days not in {7, 14, 30}
            or type(seed) is not int or not 0 <= seed <= 2**32-1):
        raise MMSValidationError("Training requires a 7/14/30-day horizon and integer seed in [0,2**32-1]")
    dates = sorted({as_date(t) for t in decision_dates})
    if not dates:
        raise MMSValidationError("Training dates are required")
    examples, versions, included, excluded = [], set(), [], []
    for t in dates:
        snapshot = provider.get_snapshot(t)
        if snapshot.analysis_date != t:
            raise MMSValidationError("Training provider returned a different date")
        future = outcomes.window(t, [r.sku_id for r in snapshot.rows], horizon_days)
        if any(o.sop_day for days in future.values() for o in days):
            excluded.append({"analysis_date": str(t), "reason": "SOP outcome window"})
            continue
        versions.add(snapshot.data_version)
        included.append(t)
        for row in snapshot.rows:
            if row.available_stock <= 0 or not row.eligible:
                continue
            features = [finite(getattr(row, name), name) for name in FEATURES]
            examples.append({"date": str(t), "sku_id": row.sku_id, "features": features,
                             "label": int(any(o.stockout for o in future[row.sku_id]))})
    if len(versions) != 1:
        raise MMSValidationError("Training requires one consistent data version")
    if data_kind == "verified" and any(v.startswith("synthetic") for v in versions):
        raise MMSValidationError("Synthetic data cannot be declared verified production data")
    if len(examples) < 20 or {e["label"] for e in examples} != {0, 1}:
        raise MMSValidationError("Training needs at least 20 eligible samples and both outcome classes")
    training_hash = hashlib.sha256(json.dumps({"examples": examples, "features": FEATURES,
        "horizon_days": horizon_days, "seed": seed, "outcome_version": outcomes.version},
        sort_keys=True, allow_nan=False).encode()).hexdigest()
    x = pd.DataFrame([e["features"] for e in examples], columns=FEATURES)
    model = HistGradientBoostingClassifier(max_iter=60, max_leaf_nodes=7, min_samples_leaf=10,
        l2_regularization=1., early_stopping=False, random_state=seed)
    model.fit(x, [e["label"] for e in examples])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mms-training-", dir=target.parent) as temporary:
        staged = Path(temporary)/"bundle"
        staged.mkdir()
        artifact = staged/"histgb.joblib"
        joblib.dump(model, artifact)
        manifest = {"artifact_version": artifact_version, "sklearn_version": sklearn.__version__,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "features": list(FEATURES),
            "positive_class": 1, "preprocessing": "embedded", "calibrated": False,
            "compatible_data_versions": sorted(versions),
            "supervised_data_cutoff": str(max(included)+timedelta(days=horizon_days)),
            "training_dates": [str(t) for t in included], "excluded_dates": excluded,
            "training_samples": len(examples), "positive_samples": sum(e["label"] for e in examples),
            "training_data_sha256": training_hash, "outcome_version": outcomes.version,
            "label_horizon_days": horizon_days, "random_seed": seed, "data_kind": data_kind,
            "label_definition": "any verified stockout in (T,T+horizon]; existing zero/negative balances excluded",
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
