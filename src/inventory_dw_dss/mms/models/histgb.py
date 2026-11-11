"""Inference only. Never trains, silently imputes, or substitutes a risk heuristic."""
import hashlib
import json
from pathlib import Path

from ..core.schemas import ArtifactError, as_date, finite


class HistGBRiskModel:
    def __init__(self, model, manifest):
        self.model = model
        self.manifest = manifest
        self.version = manifest["artifact_version"]
        self.calibrated = manifest["calibrated"]

    @classmethod
    def load(cls, artifact_path, manifest_path):
        """Only load owner-approved local joblib artifacts (pickle executes code)."""
        import joblib
        import sklearn
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.pipeline import Pipeline
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            required = {"artifact_version", "sklearn_version", "sha256", "features",
                        "positive_class", "preprocessing", "calibrated", "compatible_data_versions",
                        "supervised_data_cutoff"}
            if not required <= manifest.keys():
                raise ArtifactError("Incomplete artifact manifest")
            as_date(manifest["supervised_data_cutoff"])
            if hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest() != manifest["sha256"]:
                raise ArtifactError("Artifact checksum mismatch")
            if manifest["sklearn_version"] != sklearn.__version__:
                raise ArtifactError("Exact sklearn version must match the trained artifact")
            if manifest["preprocessing"] != "embedded" or type(manifest["calibrated"]) is not bool:
                raise ArtifactError("Preprocessing must be embedded; calibrated must be boolean")
            versions = manifest["compatible_data_versions"]
            if not isinstance(versions, list) or not versions or not all(isinstance(v, str) and v for v in versions):
                raise ArtifactError("Compatible data versions must be explicitly declared")
            features = manifest["features"]
            if (not isinstance(features, list) or not features or len(set(features)) != len(features)
                    or not all(isinstance(f, str) for f in features) or not manifest["artifact_version"]):
                raise ArtifactError("Invalid artifact feature schema/version")
            model = joblib.load(artifact_path)
            classifier = model.steps[-1][1] if isinstance(model, Pipeline) else model
            if not isinstance(classifier, HistGradientBoostingClassifier):
                raise ArtifactError("Artifact must contain a HistGradientBoostingClassifier")
            if list(getattr(model, "feature_names_in_", [])) != features:
                raise ArtifactError("Artifact feature names/order disagree with manifest")
            if len(model.classes_) != 2 or manifest["positive_class"] not in model.classes_:
                raise ArtifactError("Artifact must have two classes and a known positive class")
            return cls(model, manifest)
        except ArtifactError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ArtifactError(f"Cannot load HistGB artifact: {exc}") from exc

    def validate_snapshot(self, snapshot):
        if snapshot.data_version not in self.manifest["compatible_data_versions"]:
            raise ArtifactError("Snapshot data version is incompatible with trained artifact")
        if as_date(self.manifest["supervised_data_cutoff"]) > snapshot.analysis_date:
            raise ArtifactError("Artifact supervised-data cutoff is after the historical decision date")

    def score(self, rows):
        import pandas as pd
        import numpy as np
        if not rows:
            return ()
        values = []
        for row in rows:
            base = {"available_stock": row.available_stock, "sales_7d": row.sales_7d,
                    "sales_30d": row.sales_30d, "sales_90d": row.sales_90d,
                    "vel90": row.vel90, "dos": row.dos, "revenue_90d": row.revenue_90d,
                    "days_since_last_receipt": row.days_since_last_receipt}
            if set(base) & set(row.features):
                raise ArtifactError("Extra features may not override canonical feature values")
            base.update(row.features)
            vector = []
            for name in self.manifest["features"]:
                try:
                    vector.append(finite(base.get(name), f"feature {name}"))
                except ValueError as exc:
                    raise ArtifactError(str(exc)) from exc
            values.append(vector)
        probabilities = np.asarray(self.model.predict_proba(pd.DataFrame(values, columns=self.manifest["features"])))
        if probabilities.shape != (len(rows), 2) or not np.isfinite(probabilities).all():
            raise ArtifactError("Invalid artifact probability output")
        scores = probabilities[:, list(self.model.classes_).index(self.manifest["positive_class"])]
        if ((scores < 0) | (scores > 1)).any():
            raise ArtifactError("Risk scores must be in [0,1]")
        return tuple(float(v) for v in scores)
