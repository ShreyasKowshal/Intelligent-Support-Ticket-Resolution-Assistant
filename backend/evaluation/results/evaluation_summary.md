# Phase 9 evaluation summary

This run uses an isolated seeded SQLite database, the pinned sentence encoder, the 16 held-out retrieval queries, and deterministic fake LLM outputs. The metrics below never call Gemini; optional `--live` output is kept separately. The corpus and labels are small and synthetic; results are prototype diagnostics, not production performance estimates.

## Complaint analysis

| Field | Accuracy | Macro precision | Macro recall | Macro F1 |
| --- | ---: | ---: | ---: | ---: |
| category | 50.0% | 51.9% | 57.7% | 51.8% |
| intent | 50.0% | 51.9% | 57.7% | 51.8% |
| product | 68.8% | 76.0% | 75.0% | 73.5% |
| severity | 56.2% | 51.0% | 51.0% | 47.9% |
| sentiment | 25.0% | 41.7% | 53.8% | 31.7% |

Needs-review accuracy: **93.8%**; positive-class recall: **0.0%**; unknown-category normalization: **PASS**.
These are **label-blind nearest-ticket fake-provider scores**. The surrogate uses approved ticket complaint text, not evaluation labels. They exercise the analysis path and provide a reproducible reference, but do not measure Gemini accuracy. Intent is free text in live output; exact intent-label scoring here applies only to the surrogate's fixed categories.

## Retrieval: FAISS versus TF-IDF

| Evidence | Method | Queries | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Resolved tickets | FAISS semantic | 12 | 16.7% | 41.7% | 58.3% | 0.367 |
| Resolved tickets | TF-IDF | 12 | 0.0% | 41.7% | 41.7% | 0.205 |
| KB articles | FAISS semantic | 16 | 31.2% | 65.6% | 93.8% | 0.705 |
| KB articles | TF-IDF | 16 | 21.9% | 43.8% | 62.5% | 0.558 |

Both methods index the same approved ticket/KB text and search only the complaint. Ticket resolution text is excluded. MRR uses the full ranking. An unlabeled evidence type is excluded rather than counted as a miss. Recall@K is the fraction of labeled relevant IDs retrieved per query. The ticket labels identify one anchor ID per issue family; other valid same-family tickets can be scored as misses, so this is a conservative ID-level test.
Exact held-out/indexed complaint duplicates: **0**; near matches (text ratio ≥ 0.90): **0**. Ticket embedding text excludes resolutions: **True**.
This small synthetic benchmark is useful for finding ranking errors, but broader human relevance judgments and real complaint language are needed before production.

## RAG structural checks

| Check | Result |
| --- | --- |
| Cited ID validity against retrieved approved evidence | 100.0% |
| Step citation coverage | 100.0% |
| Hallucinated ID rejected | PASS |
| Invalid textual reference rejected | PASS |
| Empty evidence abstains | PASS |
| Weak evidence abstains | PASS |
| Compliant fake follows KB preference | PASS |
| Validator rejects conflicting ticket advice | FAIL |
| Injected invented ID rejected | PASS |
| Prompt marks complaint/evidence as untrusted | PASS |
| Injected harmful advice with valid ID rejected | FAIL |

Citation checks are useful for rejecting invented IDs and unsupported empty-evidence drafts. **They do not prove semantic entailment or enforce KB precedence** when a provider cites a real but conflicting ticket. Prompt text tells the model to ignore untrusted instructions, yet harmful advice with a valid source ID can pass structural validation. Those cases require human review or a stronger evidence verifier.

## System and health

| Route | Runs | Mean | Median | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| /analyze | 7 | 1.0 ms | 1.1 ms | 0.8 ms | 1.2 ms |
| /search | 7 | 20.0 ms | 19.7 ms | 18.4 ms | 21.8 ms |
| /resolve | 7 | 21.6 ms | 22.0 ms | 20.5 ms | 22.6 ms |

`/health`: HTTP 200; `/ready`: HTTP 200. Database=True, search index=True, embedding model=True, provider configured=True (fake provider).
Latency is from FastAPI `latency_ms` after one warm request per route. It includes local model/search work but excludes cold load, network transport, and live Gemini time. `/ready` checks configuration, not provider network reachability. Latency varies by machine and is not byte-stable across runs.

## Interpretation

The service paths, eligibility checks, and citation guardrails are exercised and suitable for a controlled prototype demo. Retrieval quality must be judged against the side-by-side baseline above; do not assume semantic retrieval wins every metric. The analysis surrogate and RAG fake-provider scores are diagnostics only. Real complaint classification, step relevance, KB conflict handling, and production latency still need live and human evaluation. Run `--live` separately for a small Gemini sample when provider connectivity is available; its output is not merged into these metrics.
