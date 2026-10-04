# Project handoff

Phases **1–10 are complete**. This handoff reflects the code through `6cbad92`
and the latest completed local checks on 2026-10-04. `develop` is the active
branch; `main` remains unmerged. For full setup, API, and evaluation details,
see [README](../README.md); for service settings, see the
[Render deployment guide](RENDER_DEPLOYMENT.md).

## Original problem, goal, and schedule

Prodapt's telecom support use case asks an agent-facing assistant to classify
a raw complaint by intent/category, product, severity, and sentiment; retrieve
semantically similar resolved tickets and knowledge-base (KB) articles; and
draft grounded, step-by-step guidance with source citations. It must also
handle new or updated tickets, KB guidance, and ticket classes. Keyword search
alone misses paraphrases. Synthetic or open data is allowed. The deliverables
are executable GitHub code, an architecture diagram, additional exploration,
system-health evaluation, and production-scale considerations.

The original target was a feature-complete prototype by October 5, 2026,
ahead of technical evaluation on October 8; October 6–7 were reserved for
review, testing, demo practice, and necessary fixes.

## Current architecture and stack

```text
Agent browser -> Streamlit frontend -> FastAPI /resolve
                                      -> Gemini complaint analysis
                                      -> actionability decision
                                         -> non-actionable: clarification; skip search/RAG
                                         -> actionable: FastEmbed/ONNX MiniLM
                                            -> separate FAISS ticket and KB indexes
                                            -> approved evidence -> Gemini RAG
                                            -> citation validation -> agent-reviewed draft

Agent browser -> browser-origin /ready wake attempts -> Render backend
Streamlit server -> /ready polling -> backend status and submit gating
FastAPI /admin + ingestion CLI -> tickets, KB, taxonomy, embeddings in database
Database: SQLite locally; Render Postgres hosted
```

Python 3.12, FastAPI/Uvicorn, SQLAlchemy Core, Pydantic, FastEmbed/ONNX Runtime,
FAISS `IndexFlatIP`, Google Gen AI SDK, Streamlit, and HTTPX form the runtime;
scikit-learn supports evaluation. The frontend calls FastAPI, not Gemini.
The current 384-dimensional, normalized encoder is the
`sentence-transformers/all-MiniLM-L6-v2` family via ONNX artifact
`qdrant/all-MiniLM-L6-v2-onnx` (revision
`d13954661f83248295ba75c1ed411eef3b7b936e`, runtime ID
`fastembed-onnx-v1`). Runtime/model versioning prevents reuse of old
PyTorch embeddings. Tickets, KB, taxonomy, and versioned embeddings are
durable in the database; FAISS files and model cache are rebuildable local
artifacts. Missing or stale indexes rebuild from stored embeddings where
possible. See the [README architecture](../README.md) for the full diagram.

## Git and phase workflow

Work on `develop`; keep `main` as the unmerged stable milestone. The phase
workflow is PLAN → IMPLEMENT → VERIFY → REVIEW → FIX BLOCKER/HIGH → REGRESSION
TEST → COMMIT → PUSH to `origin/develop` → REPORT. Keep commits focused; never
force-push, rewrite history, or commit `.env` or secrets. Merge to `main` only
on explicit request. Phase 10 pushed deployment code before deployment and
final documentation after hosted validation.

## Completed phases

1. **Phase 1 — setup:** Established the repository layout, configuration,
   requirements, `.gitignore`, FastAPI `/health`, and initial test. Commit
   `6c66f04` (`Setup project structure`).
2. **Phase 2 — data and storage:** Built SQLAlchemy Core storage for tickets,
   KB, taxonomy, and embeddings plus validated, idempotent synthetic seeding.
   Twelve issue families yielded 120 tickets and 24 KB articles; 96 resolved,
   approved tickets and 22 approved KB articles are eligible evidence.
   Commit `19664ac` (`Add ticket dataset`).
3. **Phase 3 — semantic retrieval:** Added normalized MiniLM vectors, separate
   ticket/KB FAISS indexes, source-ID mappings, versioned embeddings, and
   approval checks. Ticket search text excludes historical resolution text.
   The original sentence-transformers revision
   `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` is historical; Phase 10
   replaced its runtime. Commit `1049042` (`Add semantic search`).
4. **Phase 4 — complaint analysis:** Isolated Gemini behind `LLMClient` and
   added typed analysis, taxonomy handling, normalized severity/sentiment,
   and `needs_review` for uncertain or unfamiliar classes. Tests use fake
   providers. Commit `6df182b` (`Add complaint analysis`).
5. **Phase 5 — cited RAG:** Bounded retrieved context, requested numbered
   steps and exact source IDs, validated ID and textual citations, and added
   weak-evidence abstention. The prompt prioritizes approved KB guidance over
   conflicting historical tickets. Commits `7a62cb8` (`Add RAG resolution`)
   and `ec18a92` (`Validate textual citations`).
6. **Phase 6 — evolving data:** Added controlled ticket/KB upserts, reviewer-
   approved taxonomy additions, embedding/index refresh, and restart reload.
   An optical-signal class-and-ticket demo confirmed search after reload.
   Commit `fb7093d` (`Add evolving data support`).
7. **Phase 7 — API:** Added `/health`, `/ready`, `/analyze`, `/search`,
   `/resolve`, and guarded ticket/KB/taxonomy admin routes. Typed contracts,
   validation, sanitized errors, latency fields, privacy-safe logging, CORS,
   and reused services support the workflow. Commits `ef053a1`
   (`Add FastAPI routes`) and `9d401b1` (`Reject noncanonical citations`).
8. **Phase 8 — frontend:** Added Streamlit complaint input and the six result
   areas: analysis, similar tickets, KB, resolution, sources, and system
   information. It handles insufficient evidence, provider errors, and
   `API_BASE_URL`. The original sample controls were removed later.
   Commit `7a0d8c6` (`Add Streamlit frontend`).
9. **Phase 9 — formal evaluation:** Added isolated-seed evaluation with a
   deterministic, label-blind fake provider for analysis, real FAISS retrieval
   on held-out queries, a same-text TF-IDF baseline, scripted RAG checks, and
   saved results in [evaluation outputs](../backend/evaluation/results/).
   Fake-provider metrics are **not Gemini accuracy**; optional live checks
   remain separate. Commit `082ff7a` (`Add evaluation framework`).
10. **Phase 10 — deployment and finalization:** Deployed FastAPI, Streamlit,
    and Render Postgres. FastEmbed/ONNX replaced PyTorch, lowering measured
    local peak memory from 535.7 to 282.2 MiB for Render Free. Hosted Gemini,
    retrieval, cited resolution, and UI flow passed; deployment docs and
    production-scale considerations were completed. Cold-start variability
    remains. Key commits: `1b3ca33` and `1d3cb60`.

## Post-Phase-10 hardening

The frontend gained a compact readiness indicator, submit gating, and a
browser-origin `/ready` wake lifecycle with bounded attempts at **0, 25, and
75 seconds**. Wake URLs use lifecycle/retry cache-busting parameters;
server-side readiness polls about every five seconds for up to **180 seconds**,
and manual Retry starts a fresh lifecycle (`2459f91`). Complaint input is
limited to **3000 characters**; 3001 or more is rejected without truncation.

The actionability guard now asks for clarification before retrieval/RAG for
nonsense, casual or non-telecom input, pure device hardware faults, local
computer/OS login problems, extremely vague telecom complaints, and
educational telecom queries. Mixed hardware plus a real telecom fault,
genuine provider account-access issues, and short specific complaints such
as “No signal.” still proceed. Relevant commits include speaker handling
`62fa0db`, mixed/account handling `bc29b2f`, vague-complaint handling
`64162ca`, and broader local-access/educational/casual handling `6cbad92`.
The latest completed local suite passed **224 backend + 59 frontend = 283
tests**.

## Current evaluation summary

| Retrieval benchmark | FAISS Recall@5 | FAISS MRR | TF-IDF Recall@5 |
| --- | ---: | ---: | ---: |
| Resolved tickets (12 labeled queries) | **58.3%** | **0.367** | 41.7% |
| KB articles (16 labeled queries) | **93.8%** | **0.705** | 62.5% |

The scripted 16-query RAG run had **100% citation-ID validity** and **100%
step citation coverage** against retrieved approved evidence. These
structural checks **do not prove semantic entailment**: a valid source ID can
still accompany unsupported, conflicting, or harmful advice. Similarity
scores are ranking scores, not calibrated probabilities. The deterministic
fake-provider analysis results test the evaluator, **not Gemini accuracy**;
live Gemini classification accuracy has not been formally measured. Sparse
relevance labels can undercount useful same-family ticket matches. Full
metrics, methods, and saved outputs are in
[backend/evaluation/results/](../backend/evaluation/results/) and the
[README](../README.md).

## Design constraints and known limitations

- Only resolved and approved tickets and approved KB articles are eligible
  evidence. Search rechecks database eligibility; index manifests detect
  stale or missing rebuildable files. New classes use reviewed taxonomy
  updates rather than model retraining.
- The synthetic corpus and sparse labels limit real-world generalization.
  Actionability heuristics can still misclassify edge cases; live Gemini
  accuracy and semantic grounding are not formally established. An agent
  must verify every draft and citation before advising a customer.
- `ADMIN_API_KEY` is a shared prototype guard, not identity-based RBAC or a
  durable approval audit trail. The backend uses one worker and a shared
  service lock, favoring correctness over concurrent throughput.
- Render Free cold starts are variable and have been intermittent. A manual
  `/ready` wake once took roughly ten minutes; the latest browser retry
  sequence has no recorded sleeping-backend hosted validation. Linux peak
  memory, first model download time, and restart persistence were not
  separately measured. `/ready` checks Gemini configuration, not network
  reachability. This remains a production-minded prototype, not a fully
  production-ready service.
- `.env`, local SQLite, model cache, and FAISS files are ignored by Git.
  Credentials belong in environment variables. For scaling, security,
  observability, privacy, and data-governance options, see the
  [README](../README.md).

## Current deployment / verification status

The hosted [FastAPI backend](https://support-ticket-assistant-api.onrender.com)
and [Streamlit frontend](https://support-ticket-assistant-ui.onrender.com) use
Render Postgres in Singapore; external database access is disabled. `/health`
and `/ready` returned 200, with readiness confirming database, search index,
embedding model, and Gemini configuration. The backend's one-worker setup and
seed/start commands are recorded in the [Render guide](RENDER_DEPLOYMENT.md).
Direct local Gemini SDK access and the full local Streamlit-to-citations flow
were also verified on the user's laptop.

On **October 2, 2026**, a hosted broadband complaint passed the full
Streamlit → FastAPI → Postgres → Gemini → retrieval → RAG → citations → UI
flow. The direct `/resolve` response contained five ticket matches, five KB
articles, cited steps, and an escalation recommendation at 3,048 ms backend
latency; the UI displayed the cited draft and agent-review warning at
3,192 ms backend processing time. A separate out-of-domain API check
abstained with no ticket matches. The current local suite result above and
later hardening do not establish that every newer hosted edge case or a
genuinely sleeping backend has been revalidated. Hosted reliability and
quality still need human review.

## Run locally

Use a Python 3.12 environment. From the repository root, install
`backend/requirements.txt` and `frontend/requirements.txt`. From `backend/`
run the following commands (the last starts the API):

```text
python -m app.seed
python -m app.build_indexes
python -m evaluation.run_evaluation
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal at the repository root, run
`python -m streamlit run frontend/app.py`. The frontend defaults to
`http://127.0.0.1:8000` unless `API_BASE_URL` is set. Run
`python -m pytest -q frontend/tests` from the root. The API reads
`GEMINI_API_KEY` from the ignored repository-root `.env` or environment;
`.env.example` documents configuration. Evaluation `--live` is optional and
kept separate from deterministic results. See the [README](../README.md) for
full setup and the [Render guide](RENDER_DEPLOYMENT.md) for hosted settings.
