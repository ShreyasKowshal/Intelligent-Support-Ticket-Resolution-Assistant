"""Run all deterministic evaluation checks against an isolated seeded database."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.engine import URL

from app.search import SemanticSearch
from app.seed import seed_database
from app.storage import Repository
from evaluation.evaluate_analysis import evaluate as evaluate_analysis
from evaluation.evaluate_rag import evaluate as evaluate_rag
from evaluation.evaluate_retrieval import evaluate as evaluate_retrieval
from evaluation.evaluate_system import evaluate as evaluate_system

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_summary(analysis: dict, retrieval: dict, rag: dict, system: dict) -> str:
    lines = [
        "# Phase 9 evaluation summary", "",
        "This run uses an isolated seeded SQLite database, the pinned sentence encoder, "
        "the 16 held-out retrieval queries, and deterministic fake LLM outputs. The metrics "
        "below never call Gemini; optional `--live` output is kept separately. "
        "The corpus and labels are small and synthetic; results are prototype diagnostics, "
        "not production performance estimates.", "",
        "## Complaint analysis", "",
        "| Field | Accuracy | Macro precision | Macro recall | Macro F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for field in ("category", "intent", "product", "severity", "sentiment"):
        values = analysis["fields"][field]
        lines.append(
            f"| {field} | {_percent(values['accuracy'])} | {_percent(values['macro_precision'])} | "
            f"{_percent(values['macro_recall'])} | {_percent(values['macro_f1'])} |"
        )
    review = analysis["needs_review"]
    lines += [
        "",
        f"Needs-review accuracy: **{_percent(review['accuracy'])}**; "
        f"positive-class recall: **{_percent(analysis['needs_review_positive']['recall'])}**; "
        f"unknown-category normalization: **{'PASS' if analysis['unknown_category_passed'] else 'FAIL'}**.",
        "These are **label-blind nearest-ticket fake-provider scores**. The surrogate uses "
        "approved ticket complaint text, not evaluation labels. They exercise the analysis "
        "path and provide a reproducible reference, but do not measure Gemini accuracy. "
        "Intent is free text in live output; exact intent-label scoring here applies only "
        "to the surrogate's fixed categories.",
        "", "## Retrieval: FAISS versus TF-IDF", "",
        "| Evidence | Method | Queries | Recall@1 | Recall@3 | Recall@5 | MRR |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for kind, label in (("tickets", "Resolved tickets"), ("kb_articles", "KB articles")):
        for method, name in (("faiss", "FAISS semantic"), ("tfidf", "TF-IDF")):
            values = retrieval[method][kind]
            lines.append(
                f"| {label} | {name} | {values['queries']} | "
                f"{_percent(values['recall_at_1'])} | {_percent(values['recall_at_3'])} | "
                f"{_percent(values['recall_at_5'])} | {values['mrr']:.3f} |"
            )
    audit = retrieval["leakage_audit"]
    lines += [
        "",
        "Both methods index the same approved ticket/KB text and search only the complaint. "
        "Ticket resolution text is excluded. MRR uses the full ranking. An unlabeled evidence "
        "type is excluded rather than counted as a miss. Recall@K is the fraction of labeled "
        "relevant IDs retrieved per query. The ticket labels identify one anchor "
        "ID per issue family; other valid same-family tickets can be scored as misses, so this "
        "is a conservative ID-level test.",
        f"Exact held-out/indexed complaint duplicates: **{len(audit['exact_ticket_complaint_duplicates'])}**; "
        f"near matches (text ratio ≥ 0.90): **{len(audit['near_ticket_complaint_matches_ratio_ge_0_9'])}**. "
        f"Ticket embedding text excludes resolutions: **{audit['ticket_text_excludes_resolution']}**.",
        "This small synthetic benchmark is useful for finding ranking errors, but broader "
        "human relevance judgments and real complaint language are needed before production.",
        "", "## RAG structural checks", "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Cited ID validity against retrieved approved evidence | {_percent(rag['citation_validity_rate'])} |",
        f"| Step citation coverage | {_percent(rag['citation_coverage'])} |",
    ]
    checks = (
        ("Hallucinated ID rejected", "invalid_id_rejected"),
        ("Invalid textual reference rejected", "textual_invalid_reference_rejected"),
        ("Empty evidence abstains", "empty_evidence_abstains"),
        ("Weak evidence abstains", "weak_evidence_abstains"),
        ("Compliant fake follows KB preference", "kb_preference_observed_with_compliant_fake"),
        ("Validator rejects conflicting ticket advice", "conflicting_ticket_advice_rejected_by_validator"),
        ("Injected invented ID rejected", "injected_hallucinated_id_rejected"),
        ("Prompt marks complaint/evidence as untrusted", "untrusted_text_instruction_present"),
        ("Injected harmful advice with valid ID rejected", "injected_instruction_with_valid_id_rejected_by_validator"),
    )
    for label, key in checks:
        lines.append(f"| {label} | {'PASS' if rag[key] else 'FAIL'} |")
    lines += [
        "",
        "Citation checks are useful for rejecting invented IDs and unsupported empty-evidence "
        "drafts. **They do not prove semantic entailment or enforce KB precedence** when a "
        "provider cites a real but conflicting ticket. Prompt text tells the model to ignore "
        "untrusted instructions, yet harmful advice with a valid source ID can pass structural "
        "validation. Those cases require human review or a stronger evidence verifier.",
        "", "## System and health", "",
        "| Route | Runs | Mean | Median | Min | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for path in ("/analyze", "/search", "/resolve"):
        values = system["routes"][path]
        lines.append(
            f"| {path} | {values['runs']} | {values['mean_ms']:.1f} ms | "
            f"{values['median_ms']:.1f} ms | {values['min_ms']:.1f} ms | "
            f"{values['max_ms']:.1f} ms |"
        )
    lines += [
        "",
        f"`/health`: HTTP {system['health']['status_code']}; "
        f"`/ready`: HTTP {system['ready']['status_code']}. "
        f"Database={system['ready']['database']}, search index={system['ready']['search_index']}, "
        f"embedding model={system['ready']['embedding_model']}, "
        f"provider configured={system['ready']['gemini_configured']} (fake provider).",
        "Latency is from FastAPI `latency_ms` after one warm request per route. "
        "It includes local model/search work but excludes cold load, network transport, and "
        "live Gemini time. `/ready` checks configuration, not provider network reachability. "
        "Latency varies by machine and is not byte-stable across runs.",
        "", "## Interpretation", "",
        "The service paths, eligibility checks, and citation guardrails are exercised and "
        "suitable for a controlled prototype demo. Retrieval quality must be judged against "
        "the side-by-side baseline above; do not assume semantic retrieval wins every metric. "
        "The analysis surrogate and RAG fake-provider scores are diagnostics only. Real complaint "
        "classification, step relevance, KB conflict handling, and production latency still "
        "need live and human evaluation. Run `--live` separately for a small Gemini sample "
        "when provider connectivity is available; its output is not merged into these metrics.",
        "",
    ]
    return "\n".join(lines)


def run(output_dir: Path = RESULTS_DIR, live: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="support-evaluation-") as directory:
        root = Path(directory)
        repository = Repository(URL.create("sqlite", database=str(root / "evaluation.db")))
        try:
            seed_database(repository)
            search = SemanticSearch(repository, index_dir=root / "indexes")
            search.load_or_build()
            analysis = evaluate_analysis(repository)
            retrieval = evaluate_retrieval(repository, search)
            rag = evaluate_rag(repository, search)
            if live:
                from evaluation.evaluate_live import evaluate as evaluate_live
                _write_json(output_dir / "live_sample.json", evaluate_live(repository, search))
            system = evaluate_system(repository, search)
        finally:
            repository.close()
    results = {
        "analysis_metrics.json": analysis,
        "retrieval_metrics.json": retrieval,
        "rag_metrics.json": rag,
        "latency_metrics.json": system,
    }
    for name, data in results.items():
        _write_json(output_dir / name, data)
    (output_dir / "evaluation_summary.md").write_text(
        render_summary(analysis, retrieval, rag, system), encoding="utf-8",
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--live", action="store_true", help="Optional three-complaint Gemini sample")
    args = parser.parse_args()
    results = run(args.output_dir, live=args.live)
    print(f"Wrote deterministic evaluation to {args.output_dir}")
    print(f"Analysis cases: {results['analysis_metrics.json']['samples']}; "
          f"retrieval queries: {len(results['retrieval_metrics.json']['per_query'])}; "
          f"RAG cases: {results['rag_metrics.json']['queries']}")
    if args.live:
        live_result = json.loads((args.output_dir / "live_sample.json").read_text(encoding="utf-8"))
        print(f"Live Gemini sample: {live_result['status']}")


if __name__ == "__main__":
    main()
