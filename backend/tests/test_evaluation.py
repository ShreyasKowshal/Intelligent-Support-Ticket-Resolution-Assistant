"""Metric and harness regression tests; no live provider calls."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis import ComplaintAnalysis
from app.llm import FakeLLMClient
from app.rag import GroundingError, RAGGenerator
from app.search import KBMatch, SemanticSearch
from evaluation.evaluate_retrieval import TfidfBaseline
from evaluation.metrics import citation_coverage, classification_metrics, latency_metrics, ranking_metrics
from evaluation.run_evaluation import run


def test_recall_and_mrr_use_first_of_multiple_relevant_ids():
    scores = ranking_metrics([(["X", "B", "Y", "A"], {"A", "B"}), (["A", "X"], {"A"})])
    assert scores == {
        "queries": 2, "recall_at_1": 0.5, "recall_at_3": 0.75,
        "recall_at_5": 1.0, "mrr": 0.75,
    }


def test_ranking_without_relevant_result_scores_zero():
    scores = ranking_metrics([(["X", "Y"], {"A"}), (["X"], set())])
    assert all(scores[key] == 0 for key in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr"))
    with pytest.raises(ValueError, match="duplicate"):
        ranking_metrics([(["A", "A"], {"A"})])


def test_macro_f1_is_unweighted_across_classes():
    scores = classification_metrics(["a", "a", "a", "b"], ["a", "a", "a", "a"])
    assert scores["accuracy"] == 0.75
    assert scores["macro_f1"] == 0.4286
    assert scores["macro_recall"] == 0.5


def test_tfidf_baseline_ranks_shared_searchable_text():
    baseline = TfidfBaseline(
        ["T-001", "T-002"],
        ["Complaint: evening broadband dropout Product: broadband",
         "Complaint: missing invoice payment Product: mobile_postpaid"],
    )
    assert baseline.rank("invoice payment missing")[0] == "T-002"
    assert baseline.rank("broadband dropout")[0] == "T-001"


def test_citation_coverage_and_latency_aggregation():
    steps = [SimpleNamespace(source_ids=["KB-001"]), SimpleNamespace(source_ids=[])]
    assert citation_coverage(steps) == 0.5
    assert citation_coverage([]) == 0
    assert latency_metrics([1.0, 3.0, 5.0]) == {
        "runs": 3, "mean_ms": 3.0, "median_ms": 3.0, "min_ms": 1.0, "max_ms": 5.0,
    }


def test_rag_rejects_hallucinated_id():
    analysis = ComplaintAnalysis(
        intent="restore service", category="broadband_connectivity", product="broadband",
        severity="HIGH", sentiment="NEUTRAL", confidence=0.8, needs_review=False,
        rationale="Broadband fails.",
    )
    response = {
        "problem_summary": "A line issue", "resolution_steps": [{
            "step_number": 1, "action": "Follow guidance.", "source_ids": ["KB-999"],
        }], "escalation_recommendation": "Escalate if needed.",
        "confidence_or_evidence_note": "Limited evidence.",
        "sources_used": ["KB-999"], "insufficient_evidence": False,
    }
    evidence = [KBMatch("KB-001", "Line guidance", "Check the status light.",
                        "broadband_connectivity", 0.8)]
    with pytest.raises(GroundingError):
        RAGGenerator(FakeLLMClient({}, response)).generate("My line drops", analysis, [], evidence)


class ConstantEncoder:
    dimension = 4

    def encode(self, texts):
        return np.asarray([[1.0, 0.0, 0.0, 0.0] for _ in texts], dtype=np.float32)


def test_runner_is_key_free_and_quality_artifacts_are_reproducible(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "evaluation.run_evaluation.SemanticSearch",
        lambda repository, index_dir: SemanticSearch(repository, ConstantEncoder(), index_dir),
    )
    first = tmp_path / "first"
    second = tmp_path / "second"
    results = run(first)
    run(second)
    for name in ("analysis_metrics.json", "retrieval_metrics.json", "rag_metrics.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert not (first / "live_sample.json").exists()
    assert "GEMINI_API_KEY" not in (first / "evaluation_summary.md").read_text(encoding="utf-8")
    assert results["analysis_metrics.json"]["provider_receives_reference_labels"] is False
    rag = results["rag_metrics.json"]
    assert rag["invalid_id_rejected"] is True
    assert rag["injected_hallucinated_id_rejected"] is True
    assert rag["injected_instruction_with_valid_id_rejected_by_validator"] is False
