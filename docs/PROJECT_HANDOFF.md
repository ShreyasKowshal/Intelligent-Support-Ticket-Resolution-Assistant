# Project handoff

Updated after Phase 10 hosted validation on 2026-10-02. The `develop` checkout,
code, tests, and `backend/evaluation/results/` are the source of truth. See the
README for setup and the Render runbook for deployed service configuration.

## Original problem, goal, and schedule

Prodapt's telecom support use case asks an agent-facing assistant to parse a raw
complaint into intent/category, product, severity, and sentiment; retrieve
semantically similar past resolved tickets and KB articles; and draft a grounded,
step-by-step resolution with historical evidence and citations. It must adapt
to new tickets, updated guidance, and new ticket classes. Synthetic or open
data is allowed. Deliverables include executable GitHub code, a microservice
architecture diagram, data exploration, system-health evaluation, and
production-scale considerations. Keyword search alone misses paraphrases.

The working target is a feature-complete prototype by **Monday, October 5,
2026**, with technical evaluation on **Thursday, October 8, 2026**. October
6–7 are for review, testing, demo practice, and necessary fixes.

## Current architecture and stack

```text
Streamlit agent page (frontend/app.py)
    -> HTTP POST /resolve on FastAPI
        -> complaint analysis (Gemini via LLMClient)
        -> semantic search (pinned MiniLM via FastEmbed ONNX + separate FAISS indexes)
             -> approved/resolved tickets and approved KB from Repository
        -> cited RAG draft (Gemini via LLMClient) + citation validation

FastAPI also exposes /health, /ready, /analyze, /search, and guarded /admin
ticket, KB, and taxonomy updates. The CLI uses the same ingestion service.

Repository -> SQLite locally / Render Postgres hosted.
```

Python 3.12 is the documented local target. FastAPI/Uvicorn, SQLAlchemy Core,
Pydantic, FastEmbed/ONNX Runtime, FAISS, Google Gen AI SDK, and Streamlit are
the main libraries. HTTPX powers the frontend client; scikit-learn powers the
Phase 9 TF-IDF baseline and metric calculations. The frontend calls FastAPI
only. It has no direct Gemini or admin workflow.

FAISS files and model cache are disposable filesystem artifacts. The database is
the durable source for tickets, KB, taxonomy, and versioned embeddings. Local
SQLite, FAISS files, model cache, and `.env` are ignored by Git. The service
rebuilds missing/stale indexes using stored embeddings where possible. The ONNX
embedding runtime has a distinct model/version identifier and index manifest;
old PyTorch vectors cannot be reused with it.

## Git and phase workflow

`develop` is active; `main` is the stable milestone. For each phase: PLAN ->
IMPLEMENT -> VERIFY -> REVIEW -> FIX BLOCKER/HIGH -> REGRESSION TEST -> COMMIT
-> PUSH to `origin/develop` -> REPORT. Use one focused commit per phase, never
force-push or rewrite history, and merge to `main` only on explicit request.
Never commit `.env`, credentials, or secrets.
Phase 10 used deployment-code commit/push before deployment and a separate
final-documentation commit/push after hosted validation.

## Completed phases

1. **Phase 1 — setup:** Repository layout, configuration, requirements,
   `.gitignore`, FastAPI `/health`, and its first test. Commit `6c66f04`
   (`Setup project structure`).
2. **Phase 2 — data/storage:** SQLAlchemy Core repository with tickets,
   `kb_articles`, taxonomy, and embeddings tables; validated synthetic seed,
   idempotent insert, profile, and held-out fixture. Twelve issue families
   expand to 120 tickets; there are 24 KB articles, 96 approved resolved
   ticket evidence records, and 22 approved KB records. Commit `19664ac`
   (`Add ticket dataset`).
3. **Phase 3 — semantic retrieval:** `all-MiniLM-L6-v2` pinned at revision
   `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; normalized vectors;
   separate FAISS ticket/KB indexes with explicit source-ID mappings and
   versioned database embeddings. Ticket search text is complaint, product,
   and category, never historical resolution. Approval is rechecked at search
   time. Commit `1049042` (`Add semantic search`).
4. **Phase 4 — complaint analysis:** Gemini SDK isolated by `LLMClient`, typed
   analysis, known-taxonomy handling, review flag, and `other` for unfamiliar
   classes. Severity and sentiment are normalized to service labels. Tests use
   fake providers. Commit `6df182b` (`Add complaint analysis`).
5. **Phase 5 — cited RAG:** Retrieves approved evidence, bounds context,
   requests numbered steps and exact citations, checks citation IDs and
   textual references, and abstains on weak evidence. Prompt tells Gemini to
   prefer approved KB over conflicting historical tickets. Commits `7a62cb8`
   (`Add RAG resolution`) and `ec18a92` (`Validate textual citations`).
6. **Phase 6 — evolving data:** Controlled ticket/KB upserts, reviewed
   taxonomy changes, index refresh, persistent embeddings, and analyzer
   taxonomy reload. The optical-signal demo adds a new class and ticket,
   confirms search, then reloads after restart. Commit `fb7093d`
   (`Add evolving data support`).
7. **Phase 7 — FastAPI routes:** `/health`, `/ready`, `/analyze`, `/search`,
   `/resolve`, and secret-guarded `/admin/tickets`, `/admin/kb`,
   `/admin/taxonomy`. Request/response models, safe error codes, bounded
   complaint and Top-K validation, privacy-safe route logging, latency fields,
   restrictive configurable CORS, and reused lifecycle services. Commits
   `ef053a1` (`Add FastAPI routes`) and `9d401b1`
   (`Reject noncanonical citations`).
8. **Phase 8 — Streamlit:** Agent complaint input, five sample complaints,
   analysis, ranked ticket and KB evidence, numbered cited resolution,
   insufficient-evidence and provider-error states, source IDs, and latency.
   `API_BASE_URL` configures the backend; HTTP requests have bounded timeouts.
   Commit `7a0d8c6` (`Add Streamlit frontend`).
9. **Phase 9 — formal evaluation:** `python -m evaluation.run_evaluation`
   builds an isolated temporary seed DB and runs label-blind fake analysis,
   real pinned-model FAISS retrieval against the 16 held-out queries, a
   same-text TF-IDF baseline, scripted RAG adversarial checks, and seven warm
   FastAPI requests per endpoint. JSON metrics and a readable summary are in
   `backend/evaluation/results/`. `--live` is optional and separate. Commit
   `082ff7a` (`Add evaluation framework`).

## Phase 9 results and interpretation

The **analysis numbers are from a label-blind nearest-ticket fake provider**,
not Gemini. On 16 manually labeled cases, category/intent accuracy are 50.0%
with macro F1 51.8%; product 68.8%/73.5%; severity 56.2%/47.9%; sentiment
25.0%/31.7%. Review-required positive recall is 0.0% for this surrogate;
separate unfamiliar-category normalization passes. These results validate
the scorer and show a weak lexical surrogate. They cannot establish live
Gemini accuracy. Live free-text intent also needs a human or rubric-based
assessment rather than exact string matching.

The retrieval benchmark uses only the raw held-out complaint as query and
explicitly labeled eligible source IDs. With **12 ticket-labeled queries**,
FAISS ticket Recall@1/3/5 is **16.7%/41.7%/58.3%**, MRR **0.367**; TF-IDF is
**0.0%/41.7%/41.7%**, MRR **0.205**. With **16 KB-labeled queries**, FAISS KB
Recall@1/3/5 is **31.2%/65.6%/93.8%**, MRR **0.705**; TF-IDF is
**21.9%/43.8%/62.5%**, MRR **0.558**. Multiple relevant IDs contribute
fractionally to Recall@K. Ticket labels identify only one anchor per issue
family, so other useful same-family tickets can score as misses. No exact
or near (text-ratio >= 0.90) held-out/indexed ticket complaint duplicates
were found. The corpus was not changed to improve scores.

Scripted RAG runs on all 16 queries had **100% cited-ID validity** against
retrieved approved evidence and **100% step citation coverage**. Invented IDs,
invalid textual references, and injected invented IDs were rejected; empty
and weak evidence abstained. A compliant fake preferred KB guidance in a
synthetic conflict. **Citation validity does not prove semantic support**:
the validator accepts real-ID citations attached to conflicting ticket advice
or injected harmful advice. These are known MEDIUM limitations requiring agent
review and, for production, stronger evidence verification.

Seven warm fake-provider in-process requests per route were measured. The
latest saved run's mean latency is in `backend/evaluation/results/` (roughly
1 ms `/analyze`, 20 ms `/search`, and 21.6 ms `/resolve` on this machine). Times
exclude cold model/index loading, HTTP transport, and live Gemini. `/health`
and `/ready` returned 200 with the temporary DB, search, model, and fake
provider ready. `/ready` does not probe Gemini's network reachability.
Quality JSON files were byte-identical across real-model reruns; latency is
expected to vary. The final local regression suite is **117 backend tests + 21
frontend tests = 138 passed**, with one Starlette/TestClient HTTPX deprecation
warning. API HTTP smoke passed `/health`, `/ready`, `/analyze`, `/search`, and
`/resolve` with a fake provider.

The user has successfully made a direct Gemini SDK call from the local laptop.
An optional Phase 9 live sample from the Codex environment failed on its first
query with `GeminiProviderError`; a keyless host probe returned `ConnectError`.
No live output was merged into deterministic scores, and no key was printed.
This appears environment-specific, not evidence of a frontend defect. Repeat
live/human evaluation on the user's reachable environment.

The user also manually verified the full live local pipeline on their laptop:
Streamlit → FastAPI → Gemini analysis → semantic retrieval → RAG generation
→ citations → frontend display. For "My broadband drops every evening around
8 PM and I already restarted the router twice.", the result showed complaint
analysis, similar resolved tickets, relevant KB articles, grounded resolution,
per-step citations, an escalation recommendation, and backend processing
latency. Direct Gemini SDK access works locally; prior Codex `ConnectError`
failures appear environment-specific.

## Design constraints and known limitations

- Evidence eligibility is resolved+approved for tickets and approved for KB.
  Search validates saved FAISS manifests and rechecks live database eligibility.
  `IngestionService` refreshes indexes after meaningful updates.
- Taxonomy additions require a reviewer through CLI/API; the API admin routes
  require `ADMIN_API_KEY`. This is a simple prototype guard, not full RBAC or
  a durable approval audit trail.
- Synthetic data and a small, sparse relevance fixture limit external
  validity. Similarity scores rank matches; they are not probabilities.
  RAG citations check IDs, not whether each step is semantically entailed.
- The pinned ONNX encoder's first download and FAISS rebuild may be slow.
  Hosted readiness and retrieval passed, but Linux peak memory, first-download
  time, and restart persistence were not separately measured. SQLite remains
  the local default; Postgres is selected through `DATABASE_URL` on Render.
- `.env` is ignored and untracked. No key or admin secret belongs in code,
  result files, logs, or Git history.

## Phase 10 deployment and validation

Deployment code was pushed to `develop` as `1b3ca33` (`Prepare Render deployment`).
The first Render Free backend attempt exceeded 512 MiB with the original
PyTorch runtime. Commit `1d3cb60` (`Reduce embedding memory`) replaced that
runtime with pinned FastEmbed/ONNX MiniLM while retaining 384-dimensional
normalized vectors, separate FAISS `IndexFlatIP` indexes, approved-evidence
rules, and a version barrier against old embeddings. Local Windows peak process
memory through readiness, rebuild, search, and fake-provider resolution was
282.2 MiB, versus 535.7 MiB for the earlier PyTorch path. This does not measure
the hosted Linux memory peak. Render's Free backend then reached Live.

The deployed services are [FastAPI](https://support-ticket-assistant-api.onrender.com)
and [Streamlit](https://support-ticket-assistant-ui.onrender.com), backed by
Render Postgres in Singapore with external database access disabled. Public
`/health` and `/ready` returned 200 on final check; readiness reported the
database, search index, embedding model, and Gemini configuration ready. A
hosted live `/resolve` for the broadband example returned 200 with analysis,
five approved ticket matches, five KB articles, cited steps, and escalation;
its backend latency was 3,048 ms. The user confirmed the same complaint through
the hosted Streamlit UI, including citations, source IDs, backend latency
(3,192 ms), and the agent-review warning. A separate hosted out-of-domain
`/resolve` request returned `insufficient_evidence=true` and zero ticket
matches. This validates individual live paths, not hosted accuracy or load.

After hosted validation, 117 backend and 21 frontend tests passed. The final
deterministic run reproduced the saved analysis, retrieval, and RAG JSON exactly.
Warm latency varies; the final run's fake-provider `/resolve` mean was 16.0 ms
on the local machine. Hosted first-download/cold-start time, restart persistence,
Linux peak memory, out-of-domain Streamlit rendering, and provider-error UI
behavior were not separately exercised. Local tests cover the latter two states.
Human review of semantic support, KB conflicts, safety, and escalation remains
required before any draft is used with a customer. Do not claim synthetic or
scripted metrics as production model quality.

## Run locally

From the repository root, create and activate a compatible Python environment,
then install `backend/requirements.txt` and `frontend/requirements.txt`.
From `backend/` run:

```text
python -m app.seed
python -m app.build_indexes
python -m evaluation.run_evaluation
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second root-level terminal run `python -m streamlit run frontend/app.py
--server.address 127.0.0.1 --server.port 8501`. Set `API_BASE_URL` in that
process to change the backend origin; the local default is
`http://127.0.0.1:8000`. Run `python -m pytest -q frontend/tests` from the
root. The API reads the ignored repository-root `.env` for `GEMINI_API_KEY`;
`.env.example` documents optional configuration. `--live` on the evaluation
command is optional, uses up to three synthetic complaints, and writes an
ignored environment-specific `live_sample.json`.

Running `streamlit run frontend/app.py` can be sensitive to the current
working directory and Python import path. With the virtual environment
activated, the verified command from the repository root is
`python -m streamlit run frontend/app.py`.
