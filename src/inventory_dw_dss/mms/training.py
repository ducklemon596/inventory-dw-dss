"""Train the stockout-risk model from mart snapshots and their observed outcomes.

Each decision date contributes one row per orderable product that still holds the stock the
target measures. Windows touched by a stocktake are dropped per product: cycle counts happen
almost daily and correct balances in ways that are not demand.
"""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from .models.risk import FEATURES, PARAMS, feature_matrix
from .models.targets import LABEL_DEFINITIONS, check_target, target_label, target_stock
from .schemas import MMSError, as_date


def training_rows(reader, outcomes, decision_dates, horizon_days, target):
    """Feature rows, labels and the dataset versions seen; also counts stocktake exclusions."""
    rows, labels, versions, dropped = [], [], set(), 0
    for t in sorted({as_date(d) for d in decision_dates}):
        snapshot = reader.snapshot(t)
        versions.add(snapshot.data_version)
        cohort = [r for r in snapshot.rows if r.eligible and target_stock(r, target) > 0]
        future = outcomes.window(t, [r.sku_id for r in cohort], horizon_days)
        for row in cohort:
            window = future[row.sku_id]
            if any(o.stocktake for o in window):
                dropped += 1
                continue
            rows.append(row)
            labels.append(target_label(row, window, target))
    return rows, labels, versions, dropped


def train(reader, outcomes, decision_dates, output_dir, version, *, horizon_days=14,
          target="pharmacy_shortfall", seed=7):
    """Fit and write `histgb.joblib` + `manifest.json` into a new directory."""
    import joblib
    import pandas as pd
    import sklearn
    from sklearn.ensemble import HistGradientBoostingClassifier

    check_target(target)
    if horizon_days not in (7, 14, 30):
        raise MMSError("horizon_days must be 7, 14 or 30 (the mart label horizons)")
    output = Path(output_dir).resolve()
    if output.exists():
        raise MMSError(f"{output} exists; write each model version to a new directory")
    dates = sorted({as_date(d) for d in decision_dates})
    rows, labels, versions, dropped = training_rows(reader, outcomes, dates, horizon_days, target)
    if len(versions) != 1:
        raise MMSError("Training dates span several mart builds; rebuild the mart and retry")
    if len(set(labels)) != 2:
        raise MMSError("Training needs both outcomes; add decision dates")

    x = pd.DataFrame(feature_matrix(rows, FEATURES), columns=list(FEATURES))
    model = HistGradientBoostingClassifier(random_state=seed, **PARAMS).fit(x, labels)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        bundle = Path(staging) / "bundle"
        bundle.mkdir()
        joblib.dump(model, bundle / "histgb.joblib")
        manifest = {
            "artifact_version": version,
            "risk_target": target,
            "label_definition": LABEL_DEFINITIONS[target],
            "label_horizon_days": horizon_days,
            "features": list(FEATURES),
            "model_params": PARAMS,
            "random_seed": seed,
            "sklearn_version": sklearn.__version__,
            "sha256": hashlib.sha256((bundle / "histgb.joblib").read_bytes()).hexdigest(),
            "compatible_data_versions": sorted(versions),
            # Labels up to this date were seen; scoring earlier dates would look ahead.
            "supervised_data_cutoff": str(dates[-1] + timedelta(days=horizon_days)),
            "training_dates": [str(t) for t in dates],
            "training_rows": len(labels),
            "positive_rows": sum(labels),
            "stocktake_rows_dropped": dropped,
            "calibrated": False,
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        bundle.rename(output)
    return {"artifact": str(output / "histgb.joblib"), "manifest": str(output / "manifest.json"),
            "training_rows": len(labels), "positive_rows": sum(labels),
            "supervised_data_cutoff": manifest["supervised_data_cutoff"]}
