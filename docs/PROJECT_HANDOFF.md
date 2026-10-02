# Project handoff

Verified against the `develop` checkout and Git history on 2026-10-02, after Phase 6 implementation. This document distinguishes implemented behavior from the agreed target architecture. Start with the current code and tests when continuing the project.

## Problem, goal, and deadline

**Original use case:** Build an intelligent support ticket resolution assistant for a telecom desk. Keyword search misses complaints that describe the same issue in different words. An agent should paste a raw complaint and receive (1) intent/category, product, severity, and sentiment, (2) semantically similar resolved tickets and knowledge-base (KB) articles, and (3) an LLM-drafted, grounded, step-by-step resolution with citations to the evidence used. The system must accommodate evolving data and new ticket classes. Synthetic or open-source data is allowed. Required deliverables include an architecture diagram, executable code in GitHub, data exploration, health/evaluation results, and production-scale considerations.

**Schedule:** Feature-complete prototype by **Monday, October 5, 2026**; technical evaluation **Thursday, October 8, 2026**. October 6–7 are primarily for understanding the code, testing, demo rehearsal, and important fixes. Prioritize a reliable, explainable prototype without dropping required functionality or adding unnecessary infrastructure.

## Architecture and stack

```text
Target: Streamlit agent UI -> FastAPI service -> complaint analysis (LLM)
                                        |-> semantic retrieval -> grounded RAG (LLM)
                                        |       |-> ticket FAISS index
                                        |       `-> KB FAISS index
                                        `-> storage repository -> Postgres on Render
                                                             (SQLite locally)

Current: FastAPI /health; SQLite repository + synthetic seed/profile;
         sentence-transformers/FAISS semantic search; Gemini complaint analysis;
         cited RAG; controlled ticket, KB, and taxonomy ingestion.
```

FAISS files are rebuildable search artifacts; durable ticket, KB, taxonomy, and embedding records belong in the database. The current implementation uses SQLite locally. The agreed Render design uses Postgres as the source of truth and rebuilds missing/stale FAISS files from durable embeddings. Postgres connectivity, frontend behavior, and deployment are **not implemented yet**.

Current direct Python dependencies are FastAPI, Uvicorn, HTTPX, pytest, SQLAlchemy, pandas, sentence-transformers, faiss-cpu, google-genai, and python-dotenv (`backend/requirements.txt`). Pydantic and NumPy are used through installed dependencies. The frontend dependency file is only a placeholder. Python 3.12 is the documented local target; scikit-learn is planned for the later evaluation baseline, not a direct dependency yet.

## Git and phase workflow

- `main` is the stable milestone branch; `develop` is active development. Make one focused commit per validated phase on `develop`, push to `origin/develop`, never force-push or rewrite history, and merge to `main` only when explicitly requested.
- Each phase follows **PLAN -> IMPLEMENT -> VERIFY -> REVIEW -> FIX -> FINAL VALIDATION -> COMMIT -> PUSH -> REPORT**. Inspect the existing repository, constrain changes to that phase, run relevant and prior tests plus a realistic example, classify review findings as BLOCKER/HIGH/MEDIUM/LOW, fix BLOCKER/HIGH, validate again, check Git status and secrets, then commit and report the result.

## Completed phases

### Phase 1 — repository setup

Created the `backend/`, `frontend/`, and `docs/` foundation, minimal Python packages/configuration, `.env.example`, `.gitignore`, requirements files, starter README, FastAPI `GET /health` returning `{"status":"ok"}`, and a pytest endpoint test. Key files: `backend/app/main.py`, `backend/app/config.py`, `backend/tests/test_health.py`. Verification: health/import check and **1 pytest test** (still passes in the current suite). Commit **`6c66f042306a3237b4c32dcb008c7c3e6e479a6e` — `Setup project structure`**.

### Phase 2 — dataset and storage foundation

`backend/app/storage.py` isolates SQLAlchemy Core access. Its four explicit tables are `tickets`, `kb_articles`, `taxonomy_values`, and `embeddings`. `backend/app/models.py` validates records with Pydantic. The default database is ignored `backend/data/support.db` (SQLite); `DATABASE_URL` can override it, but no Postgres driver/configuration has been added. No Alembic or migration framework is used.

`backend/data/seed/` holds **12 telecom issue families expanded to 120 tickets** (`T-001` onward), **24 KB articles** (`KB-001` onward), and controlled taxonomy: 4 products (`broadband`, `mobile_prepaid`, `mobile_postpaid`, `account_services`), 12 categories, 4 severity levels (`low`, `medium`, `high`, `critical`), and 4 sentiments (`positive`, `neutral`, `negative`, `frustrated`). Categories cover broadband connection/speed/router, billing/payment, SIM, mobile network/data, roaming/recharge, account access, and outages. Counts: 108 resolved/12 open; 96 approved/24 unapproved tickets; **96 resolved-and-approved ticket evidence records**; 22 approved KB articles. Empty resolutions on open tickets are expected.

`backend/app/seed.py` validates seed data before writing and inserts only missing IDs, so a second run adds zero records. Validation rejects missing/blank required fields, malformed records, invalid status/severity/sentiment, unknown product/category, duplicate IDs, and resolved tickets without a resolution; open tickets cannot be approved. Evidence-only repository queries require both resolved **and** approved for tickets and approved for KB. `backend/evaluation/profile.py` reports counts/distributions/missing fields. `backend/evaluation/held_out_queries.json` contains **16 paraphrased queries**, including ambiguous cases, with expected labels where appropriate and relevant approved source IDs; formal scoring is still pending.

Phase 2 verification covered initialization, seed/idempotency, persistence/retrieval, validation and duplicate protection, taxonomy, evidence filtering, and held-out data, alongside Phase 1 health: **17 pytest cases at that phase**. Current profile and tests reconfirm the counts above. Commit **`19664aca1e3dedb4dba8342fdc77e5cd5164d664` — `Add ticket dataset`**.

### Phase 3 — semantic search

`backend/app/search.py` uses pinned CPU model **`sentence-transformers/all-MiniLM-L6-v2`**, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, loaded lazily once per encoder. Ticket embedding text contains complaint, product, and category, **not resolution**; KB text contains title, content, and category. Float32 vectors are normalized. Separate exact `faiss.IndexFlatIP` indexes currently hold **96 ticket** and **22 KB** vectors. Ordered `ticket_ids`/`kb_ids` in the saved manifest map every FAISS position to a stable source ID. Similarity scores are ranking scores, not calibrated probabilities; default Top-K is 5 for each index.

Normalized embeddings are persisted as bytes in the `embeddings` table with source type/ID, model name, version (pinned model revision, text version, source-text hash), and update timestamp. `backend/app/build_indexes.py` builds and saves ignored FAISS files and a checksum/source-signature manifest under `backend/data/indexes/`; `load_or_build()` verifies and reloads them or rebuilds using matching stored embeddings. `refresh_indexes()` is a Phase 6 hook, not an ingestion workflow. Only eligible records are indexed. Search also rechecks current approval/status in the repository before returning each hit.

Important review fixes reflected in the code: the live evidence recheck prevents a formerly approved record from leaking while an in-memory index awaits refresh; source signatures/manifest checks prevent stale or mismapped saved indexes; embedding versions include the full pinned model revision and source text; model-load failures produce a clear local cache/download error. Tests cover these safeguards, normalization, eligibility, source mapping, reload/rebuild, future refresh, and bad query/Top-K validation. The **current full suite passes 26 tests**. `backend/app/search_demo.py` demonstrated paraphrase retrieval: “I cannot surf the web over cellular, but voice chat works” returned mobile-data ticket **T-071** first (score **0.497**) and mobile-data article **KB-015** in the top five, despite different wording.

Remaining MEDIUM/LOW limitations: related but wrong KB categories can rank above the best article (e.g., a mobile-network article before mobile-data KB-015); ranking quality has not undergone the Phase 9 formal TF-IDF comparison. The synthetic corpus has limited resolution diversity. The current test run emits one Starlette/TestClient `httpx` deprecation warning. First model download needs connectivity and may produce a Windows cache warning. Commit **`1049042134076d717da83f2be5cc73336da10c4a` — `Add semantic search`**.

## Decisions and constraints to preserve

- Keep the small repository/storage layer and explicit schema. Add simple Postgres compatibility later, with SQLite for local development; introduce migration tooling only if genuinely required.
- Keep FAISS as the search index and the database as durable truth. Rebuild indexes from stored embeddings when files are absent/stale. Keep explicit source-ID mapping and evidence eligibility checks.
- Do not embed historical ticket resolutions into retrieval text; use resolutions only as approved evidence for generation. Preserve stable seed IDs, idempotent seeding, the held-out queries, and the `develop` branch workflow.
- Do not add Docker, Kafka, Kubernetes, elaborate CI, or other infrastructure during core implementation. Do not change working components merely to redesign them.

### Phase 4 — complaint analysis

`backend/app/analysis.py` validates the typed intent/category/product/severity/sentiment/confidence/review/rationale result. Unknown categories become `other` with `needs_review=true` and an optional suggestion. `backend/app/gemini_client.py` isolates the Google Gen AI SDK behind `LLMClient`; tests use `FakeLLMClient`. The configured model defaults to `gemini-3.5-flash-lite` and reads `GEMINI_API_KEY`/`GEMINI_MODEL` from the environment. The real local `.env` is ignored and untracked. Commit `6df182b` — `Add complaint analysis`.

### Phase 5 — cited RAG

`backend/app/rag.py` accepts an original complaint, structured analysis, and explicitly supplied retrieved ticket/KB matches. It bounds evidence, requires citations for each step, rejects IDs absent from retrieved context, and returns an insufficient-evidence result when no strong evidence is available. Approved KB guidance takes precedence over historical ticket behavior in the prompt. `backend/app/resolve_demo.py` demonstrates the analysis → retrieval → cited-resolution flow. Commit `7a62cb8` — `Add RAG resolution`; the checkpoint citation-validation fix is `ec18a92` — `Validate textual citations`.

### Phase 6 — evolving data and classes

`backend/app/ingestion.py` provides controlled ticket/KB upserts and reviewed taxonomy additions; `backend/app/ingest.py` is the local admin CLI. Existing IDs and `created_at` remain stable; changed records require a later `updated_at`, and changed KB guidance requires a higher version. Only resolved+approved tickets and approved KB articles are eligible. The service refreshes FAISS after searchable text or eligibility changes. `SemanticSearch` also detects external database changes before a search and reloads/rebuilds stale indexes. Unchanged vectors are reused from the durable embeddings table; superseded vector versions are removed. `backend/app/taxonomy.py` maps analysis severity/sentiment labels to canonical stored values (`ANGRY` → `negative`). Repository-backed complaint analysis reloads taxonomy per call, so a reviewed new category can be used without model retraining. `python -m backend.app.evolving_demo` demonstrates a new optical-signal class and ticket becoming searchable and surviving restart. The full suite currently passes **88 tests** with one existing Starlette/TestClient deprecation warning. The Phase 6 commit hash is the latest `develop` commit after this handoff update is committed.

## Current state and next work

Check `git status -sb` and `git log -1 --oneline` for the live state. `/health` is still the only FastAPI route; analysis, search, RAG, and ingestion run as local service functions/CLIs. There is no Streamlit app, Postgres driver/deployment, or Render service yet. Local SQLite, model cache, and FAISS files are ignored and must not be relied upon as deployable state. No real API keys are in the repository.

Remaining implementation phases, in order:

1. **Phase 7 — FastAPI service:** Expose analysis, retrieval, and resolution as validated API operations with clear health/error behavior.
2. **Phase 8 — Streamlit demo:** Agent complaint entry, analysis, ranked sources, cited resolution, and usable error states.
3. **Phase 9 — Evaluation:** Use held-out data for retrieval metrics and a TF-IDF baseline; evaluate analysis, citation grounding, latency, and system health.
4. **Phase 10 — Documentation and Render deployment:** Architecture diagram, production-scale considerations, setup/deployment guidance, Render backend/frontend services, final end-to-end checks, and demo readiness.

The Gemini provider uses `GEMINI_API_KEY` and `GEMINI_MODEL`; `.env.example` contains empty placeholders and the real local `.env` remains ignored. Render target: separate FastAPI and Streamlit services, plus Postgres. The storage interface uses SQLAlchemy Core and keeps SQLite as the local default; a Postgres driver and deployed database are still pending. Treat service-local FAISS/model files as disposable and rebuild indexes from database embeddings as needed. Confirm Render plan/resource limits and first-run model download behavior during deployment. The local taxonomy CLI requires a reviewer identifier but does not implement authentication or a durable approval audit log; those remain production hardening tasks.

## Run the project now

From repository root, with a compatible Python 3 installation:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # PowerShell; use `source .venv/bin/activate` on macOS/Linux
cd backend
python -m pip install -r requirements.txt
python -m app.seed
python -m evaluation.profile
python -m app.build_indexes
python -m app.search_demo
python -m app.search_demo --query "I cannot surf the web over cellular, but voice chat works." --tickets 3 --kb 5
python -m app.analyze_demo "My broadband drops every evening" --fake
python -m app.resolve_demo "My broadband drops every evening" --fake
python -m app.evolving_demo
python -m pytest -q
python -m uvicorn app.main:app --reload
```

Check `http://127.0.0.1:8000/health` for `{"status":"ok"}`. Run these commands after `cd backend` because imports use the `app` package. On 2026-10-02, the suite reported **88 passed, 1 warning**. The evolving-data demo changed an unknown optical-signal complaint from `other` to a reviewed category; its new ticket ranked first (similarity 0.927) and remained first after restart. The first index build may download the pinned model. The Windows PowerShell activation step may require local execution-policy configuration; invoking `.venv\Scripts\python.exe` directly is also possible.
