# Checkpoints, Evaluations and Monitoring

## Summary

The project checks retrieval ranking, citation structure, API behavior, and basic service health. Saved metrics are controlled prototype results rather than live Gemini or production monitoring results.

## Retrieval Evaluation

| Evidence | FAISS Recall@5 | FAISS MRR | TF-IDF Recall@5 |
| --- | ---: | ---: | ---: |
| Resolved tickets | 58.3% | 0.367 | 41.7% |
| KB articles | 93.8% | 0.705 | 62.5% |

Recall@5 measures the share of labeled relevant IDs found in the first five results; MRR rewards a higher-ranked first relevant result. FAISS and TF-IDF use the same approved searchable corpus and held-out complaints. This comparison tests whether semantic retrieval helps beyond a lexical baseline, but 16 synthetic queries and sparse ID labels limit generalization.

## RAG Evaluation

The saved deterministic fake-provider checks report **100% citation-ID validity** against retrieved evidence and **100% step citation coverage**. They also test abstention for empty/weak evidence and rejection of invented IDs. Adversarial checks show that a real cited ID can accompany conflicting or harmful advice. Structural citation validity does not establish semantic support; agents must review every draft.

## Analysis Evaluation

Saved analysis scores come from a label-blind fake-provider surrogate. They are not measurements of live Gemini accuracy. No formal live Gemini quality benchmark is claimed.

## Automated Tests

The latest verified run passed **241 backend tests** and **20 frontend tests**. TypeScript checking and the frontend production build also passed.

## Health and Readiness

- `GET /health` checks process liveness.
- `GET /ready` checks database access and search/index availability, reports an embedding-model flag tied to the index check, and confirms Gemini configuration.

`/ready` does not test Gemini provider reachability. Neither endpoint is a full monitoring or alerting system. Saved route timings are warm, in-process measurements that exclude network, cold start, and live Gemini time.

## Hosted Verification

A read-only pre-submission check returned HTTP 200 for the hosted React frontend, backend `/health`, and backend `/ready`. A CORS preflight from the hosted frontend origin to `/resolve` also returned HTTP 200 with the expected allowed origin. These observations do not measure live resolution quality.

## Strengths

Saved outputs, held-out labels, a TF-IDF baseline, endpoint checks, and automated tests make the main claims reproducible and bounded.

## Limitations / Production Gaps

There is no full metrics/alerting stack or deep provider monitoring. Render cold starts vary, and real complaint quality needs broader human evaluation.

## Repository Evidence

- [backend/evaluation/](../backend/evaluation/), [backend/evaluation/results/](../backend/evaluation/results/), and [backend/evaluation/held_out_queries.json](../backend/evaluation/held_out_queries.json).
- [backend/tests/](../backend/tests/), [frontend-react/src/test/](../frontend-react/src/test/), and [backend/app/main.py](../backend/app/main.py).
- [README.md](../README.md) — published metrics, setup, and limitations.
