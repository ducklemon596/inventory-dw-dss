"""Stockout-risk model (MB2): HistGradientBoosting scores from a trained bundle.

A bundle is `histgb.joblib` plus `manifest.json`. The manifest pins the feature order,
sklearn version, checksum, training cutoff and the risk target. Loading refuses anything
that does not match, because joblib executes code and a silent mismatch gives wrong scores.
"""
import hashlib
import json
from pathlib import Path

from ..data import MART_FEATURES
from ..schemas import ArtifactError, as_date
from .targets import check_target

# Row fields first, then mart columns. Missing values stay NaN for HistGB's native branch.
ROW_FEATURES = ("available_stock", "sales_7d", "sales_30d", "sales_90d", "vel90", "dos", "revenue_90d",
                "days_since_last_receipt")
FEATURES = ROW_FEATURES + MART_FEATURES
PARAMS = {"max_iter": 300, "learning_rate": .05, "max_leaf_nodes": 31, "min_samples_leaf": 50,
          "l2_regularization": 1., "early_stopping": False}


def feature_matrix(rows, names=FEATURES):
    """Feature vectors in `names` order; None becomes NaN, never zero."""
    def value(row, name):
        if name == "vel90":
            return row.daily_demand
        if name == "dos":
            return row.days_of_supply
        return row.features[name] if name in row.features else getattr(row, name, None)

    return [[float("nan") if (v := value(row, name)) is None else float(v) for name in names] for row in rows]


class RiskModel:
    def __init__(self, model, manifest):
        self.model = model
        self.manifest = manifest
        self.version = manifest["artifact_version"]
        self.target = check_target(manifest.get("risk_target", "dispensary_stockout"))
        self.horizon_days = manifest.get("label_horizon_days")

    @classmethod
    def load(cls, artifact_path, manifest_path):
        """Load a local bundle you trained or trust (joblib runs code on load)."""
        import joblib
        import sklearn
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            if hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest() != manifest["sha256"]:
                raise ArtifactError("Model file does not match the manifest checksum")
            if manifest["sklearn_version"] != sklearn.__version__:
                raise ArtifactError(f"Model was trained with sklearn {manifest['sklearn_version']}, "
                                    f"installed is {sklearn.__version__}")
            as_date(manifest["supervised_data_cutoff"])
            model = joblib.load(artifact_path)
            if list(getattr(model, "feature_names_in_", [])) != manifest["features"]:
                raise ArtifactError("Model features disagree with the manifest")
            return cls(model, manifest)
        except ArtifactError:
            raise
        except (OSError, ValueError, KeyError) as exc:
            raise ArtifactError(f"Cannot load the risk model: {exc}") from exc

    def check_snapshot(self, snapshot):
        """Refuse other datasets and decision dates inside the training labels (look-ahead)."""
        if snapshot.data_version not in self.manifest["compatible_data_versions"]:
            raise ArtifactError("The mart was rebuilt from another export; retrain the risk model")
        if as_date(self.manifest["supervised_data_cutoff"]) > snapshot.analysis_date:
            raise ArtifactError(f"The model saw outcomes up to {self.manifest['supervised_data_cutoff']}; "
                                "choose a later analysis date")

    def score(self, rows):
        """Probability-like score in [0, 1] per row, in row order."""
        import pandas as pd
        if not rows:
            return ()
        features = self.manifest["features"]
        frame = pd.DataFrame(feature_matrix(rows, features), columns=features)
        positive = list(self.model.classes_).index(1)
        return tuple(float(p) for p in self.model.predict_proba(frame)[:, positive])
