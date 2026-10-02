"""Small metric helpers shared by the evaluation scripts."""

from statistics import mean, median

from sklearn.metrics import accuracy_score, precision_recall_fscore_support


def classification_metrics(expected: list[str], predicted: list[str]) -> dict:
    if not expected or len(expected) != len(predicted):
        raise ValueError("classification labels must be nonempty and aligned")
    precision, recall, f1, _ = precision_recall_fscore_support(
        expected, predicted, average="macro", zero_division=0,
    )
    return {
        "samples": len(expected),
        "accuracy": round(float(accuracy_score(expected, predicted)), 4),
        "macro_precision": round(float(precision), 4),
        "macro_recall": round(float(recall), 4),
        "macro_f1": round(float(f1), 4),
    }


def ranking_metrics(rankings: list[tuple[list[str], set[str]]]) -> dict:
    """Recall@K counts all labeled relevant IDs; MRR uses the full ranking."""
    if not rankings:
        raise ValueError("at least one labeled query is required")
    scores = {1: [], 3: [], 5: []}
    reciprocals = []
    for ranked_ids, relevant_ids in rankings:
        if len(ranked_ids) != len(set(ranked_ids)):
            raise ValueError("a ranking contains duplicate source IDs")
        for k in scores:
            scores[k].append(
                len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)
                if relevant_ids else 0.0
            )
        first = next((position for position, source_id in enumerate(ranked_ids, 1)
                      if source_id in relevant_ids), None)
        reciprocals.append(1 / first if first is not None else 0.0)
    return {
        "queries": len(rankings),
        "recall_at_1": round(mean(scores[1]), 4),
        "recall_at_3": round(mean(scores[3]), 4),
        "recall_at_5": round(mean(scores[5]), 4),
        "mrr": round(mean(reciprocals), 4),
    }


def citation_coverage(steps: list) -> float:
    if not steps:
        return 0.0
    return round(sum(bool(step.source_ids) for step in steps) / len(steps), 4)


def latency_metrics(samples_ms: list[float]) -> dict:
    if not samples_ms or any(value < 0 for value in samples_ms):
        raise ValueError("latency samples must be nonempty and nonnegative")
    return {
        "runs": len(samples_ms),
        "mean_ms": round(mean(samples_ms), 3),
        "median_ms": round(median(samples_ms), 3),
        "min_ms": round(min(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
    }
