"""Observational metrics; undefined denominators return None, never a fake zero."""
from ..core.schemas import MMSValidationError, finite


def demand_metrics(actual, predicted):
    if len(actual) != len(predicted):
        raise MMSValidationError("Actual/predicted lengths differ")
    for value in (*actual, *predicted):
        finite(value, "demand", 0)
    denominator = sum(actual)
    return {"wape": sum(abs(p-a) for a, p in zip(actual, predicted)) / denominator if denominator else None,
            "bias": sum(p-a for a, p in zip(actual, predicted)) / denominator if denominator else None}


def risk_metrics(labels, scores, sku_ids, k):
    from sklearn.metrics import roc_auc_score
    if not len(labels) == len(scores) == len(sku_ids) or len(set(sku_ids)) != len(sku_ids):
        raise MMSValidationError("Risk metric vectors must align and SKUs must be unique")
    if type(k) is not int or k <= 0 or any(v not in (0, 1) for v in labels):
        raise MMSValidationError("Risk metrics require binary labels and positive K")
    for s in scores:
        if not 0 <= finite(s, "risk_score") <= 1:
            raise MMSValidationError("Risk score outside [0,1]")
    indices = sorted(range(len(labels)), key=lambda i: (-scores[i], sku_ids[i]))[:k]
    positives = sum(labels)
    hits = sum(labels[i] for i in indices)
    precision = hits / len(indices) if indices else None
    prevalence = positives / len(labels) if labels else None
    return {"precision_at_k": precision, "recall_at_k": hits / positives if positives else None,
            "lift": precision / prevalence if prevalence else None,
            "roc_auc": float(roc_auc_score(labels, scores)) if len(set(labels)) == 2 else None,
            "effective_k": len(indices), "cohort_size": len(labels), "positive_count": positives}
