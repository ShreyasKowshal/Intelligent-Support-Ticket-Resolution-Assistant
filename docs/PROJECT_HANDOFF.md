# Project handoff

**Phases 1–10 are complete.** `main` is the stable submission branch and already contains the finalized React frontend. `develop` is retained for future fixes.

## Original problem and goal

Build a telecom support assistant that analyzes complaints, retrieves semantically similar resolved tickets and KB articles,
and drafts grounded, cited steps for agent review. It must handle updated evidence and new ticket classes. Deliverables include
executable code, an architecture diagram, exploration, health evaluation, and production-scale considerations. See the [README](../README.md).

## Current architecture and stack

```text
Agent -> React -> FastAPI -> Gemini complaint analysis -> actionability
                         |-> clarification for non-actionable input
                         `-> FAISS ticket/KB retrieval -> Gemini RAG -> citation validation -> draft
React health/readiness checks -> backend status
Admin ingestion -> SQLAlchemy -> SQLite local / Render Postgres hosted
```

Stack: React, TypeScript, Tailwind CSS, Vite, FastAPI, Python, Gemini, FastEmbed/ONNX MiniLM, separate FAISS ticket/KB
indexes, SQLAlchemy, local SQLite, and hosted Render Postgres. Only approved evidence is retrieved; the agent reviews every draft.

## Git and phase workflow

Use focused commits on `develop` and push to `origin/develop`; do not rewrite history or commit secrets. Make future fixes on
`develop`, verify them, then merge them into `main`. Phase commits remain in Git history.

## Completed phases

1. **Phase 1 — setup:** Repository structure, configuration, dependencies, FastAPI health route, and initial tests.
2. **Phase 2 — data:** SQLAlchemy storage and synthetic telecom seed with 120 tickets and 24 KB articles; evidence eligibility tracked.
3. **Phase 3 — retrieval:** Semantic ticket/KB search with separate FAISS indexes; ticket embeddings exclude resolution text.
4. **Phase 4 — analysis:** Structured Gemini analysis for intent, category, product, severity, sentiment, and review needs.
5. **Phase 5 — RAG:** Cited resolution steps, KB preference, citation validation, and insufficient-evidence abstention.
6. **Phase 6 — evolving data:** Controlled ticket/KB updates, reviewed taxonomy additions, and index refresh across restarts.
7. **Phase 7 — API:** Health, readiness, analyze, search, resolve, and guarded admin routes with validation and safe errors.
8. **Phase 8 — frontend:** Complaint workflow with analysis, tickets, KB, resolution, sources, and system information.
9. **Phase 9 — evaluation:** Fake-provider analysis, real FAISS retrieval, TF-IDF baseline, scripted RAG checks, and saved results.
10. **Phase 10 — deployment:** FastAPI, frontend, and Postgres on Render; FastEmbed/ONNX reduced memory enough for Render Free deployment; hosted flow passed.

## Post-Phase-10 hardening

The React frontend checks backend readiness every five seconds for up to 180 seconds and offers a retry control.
Complaint input is limited to 3000 characters. Actionability clarifies nonsense, non-telecom, device,
local-login, vague, and informational input before retrieval/RAG while preserving mixed and genuine telecom complaints.
At the time of the saved evaluation, the local suite passed **224 backend + 59 frontend = 283 tests**.

## Current evaluation summary

Ticket FAISS Recall@5: **58.3%**, MRR: **0.367**. KB FAISS Recall@5: **93.8%**, MRR: **0.705**. Scripted citation-ID
validity and step citation coverage: **100%** each. Fake-provider metrics are **not Gemini accuracy**; valid citation IDs
do **not** prove semantic support, and similarity scores are rankings, not probabilities. See [saved outputs](../backend/evaluation/results/).

## Design constraints and known limitations

- Synthetic data and sparse relevance labels limit generalization.
- Live Gemini classification accuracy has not been formally measured.
- Citation validity does not establish semantic entailment; human review of
  every suggested step remains required.
- Admin access uses a shared key, not full production RBAC.
- Render Free cold starts vary; the prototype uses one backend worker.

## Current deployment status

The [backend](https://support-ticket-assistant-api.onrender.com) and [React frontend](https://support-ticket-assistant.onrender.com)
run on Render with hosted Postgres. The hosted React flow was verified; startup time can still vary. See the [Render guide](RENDER_DEPLOYMENT.md).

## Run locally

Install `backend/requirements.txt` in a Python 3.12 environment. From `backend/`, run
`python -m app.seed`, `python -m app.build_indexes`, `python -m evaluation.run_evaluation`, and `python -m pytest -q`.
Start the API with `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. From `frontend-react/`, run
`npm install`, `npm run dev`, and `npm run test` for frontend tests. The UI runs at `http://localhost:5173`.
Set `VITE_API_BASE_URL` to change the backend origin used by Vite; supply `GEMINI_API_KEY` through the backend environment or ignored `.env`.
Full setup is in the [README](../README.md).
