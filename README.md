# Intelligent Support Ticket Resolution Assistant

## Project overview

An agent-facing telecom support assistant analyzes a customer complaint, finds semantically similar resolved tickets and
knowledge-base (KB) articles, and drafts cited resolution steps for **agent review**. It supports updated evidence and new
ticket classes. Semantic search helps find related issues that keyword search can miss.

## Architecture

```mermaid
flowchart LR
    Agent[Support agent] --> UI[Streamlit] --> API[FastAPI] --> Analysis[Gemini analysis] --> Guard{Actionability}
    Guard -->|Non-actionable| Clarify[Clarification]
    Guard -->|Actionable| Search[FAISS ticket and KB search] --> RAG[Gemini RAG] --> Citations[Citation validation] --> Draft[Agent-reviewed draft]
    Search <--> DB[(Postgres hosted / SQLite local)]
    Admin[Reviewed ingestion] --> DB
```

Non-actionable input stops before retrieval/RAG. The frontend calls FastAPI, not Gemini or the database.

## Features and stack

- Structured complaint analysis: intent, category, product, severity, sentiment, and review status.
- FastEmbed/ONNX `all-MiniLM-L6-v2` embeddings with separate FAISS ticket and KB indexes.
- Cited RAG draft with insufficient-evidence abstention and an agent-review warning.
- Controlled ticket, KB, and taxonomy updates with refreshed search indexes.
- FastAPI, Streamlit, Gemini, SQLAlchemy, Render Postgres, and local SQLite.

The synthetic dataset has **120 tickets and 24 KB articles**; **96 resolved, approved tickets** and **22 approved KB articles** are eligible evidence.

## Run locally

Use Python 3.12. Create a virtual environment with `python -m venv .venv`; activate it with
`.\.venv\Scripts\Activate.ps1` (PowerShell) or `source .venv/bin/activate` (macOS/Linux).
From `backend/`, run `python -m pip install -r requirements.txt`, `python -m app.seed`, then
`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
In a second activated terminal at the repository root, run `python -m pip install -r frontend/requirements.txt`, then
`python -m streamlit run frontend/app.py`.
Backend: `http://127.0.0.1:8000`; frontend: `http://127.0.0.1:8501`. `API_BASE_URL` can override the backend origin.
Complaints are limited to **3000 characters**; longer input is rejected without truncation.

## Environment variables

| Variable | Service | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Backend | Hosted Postgres URL; unset uses local SQLite |
| `GEMINI_API_KEY` | Backend | Gemini credential |
| `GEMINI_MODEL` | Backend | Optional model override |
| `ADMIN_API_KEY` | Backend | Optional admin key; absent disables admin updates |
| `API_BASE_URL` | Frontend | Backend HTTP(S) origin |

Keep credentials in the environment or ignored `.env`, never in Git.

## API overview

`GET /health` checks liveness; `GET /ready` checks database, search/model, and Gemini configuration readiness.
`POST /analyze` returns structured analysis; `POST /search` returns similar approved evidence; `POST /resolve` returns a cited
draft or clarifies non-actionable input without retrieval/RAG. Guarded `POST /admin/tickets`, `/admin/kb`, and
`/admin/taxonomy` update reviewed support data.

Similarity scores rank matches; they are not calibrated probabilities.

## Data and retrieval

SQLite is the local default; Render Postgres stores hosted data. Only approved, resolved tickets and approved KB articles
are eligible evidence. Separate FAISS indexes serve tickets and KB; ticket embeddings exclude historical resolution text.
Controlled ingestion can update tickets, KB guidance, and taxonomy and refresh the indexes.

## Evaluation snapshot

- Tickets: FAISS Recall@5 **58.3%**, MRR **0.367**; TF-IDF Recall@5 41.7%.
- KB: FAISS Recall@5 **93.8%**, MRR **0.705**; TF-IDF Recall@5 62.5%.

Scripted citation-ID validity and step citation coverage were **100%** each. The latest suite passed **224 backend + 59
frontend = 283 tests**. Fake-provider analysis metrics are **not Gemini accuracy**; valid citation IDs do **not** prove
semantic support, and similarity scores are not probabilities. From `backend/`, run `python -m evaluation.run_evaluation`;
see [saved results](backend/evaluation/results/) for full outputs.

## Deployment

The [backend](https://support-ticket-assistant-api.onrender.com) and [frontend](https://support-ticket-assistant-ui.onrender.com)
run on Render with hosted Postgres. Hosted end-to-end flow and the latest sleeping-backend frontend-only wake test worked;
Render Free startup time can still vary. See the [Render deployment guide](docs/RENDER_DEPLOYMENT.md).

## Limitations

- Synthetic data and sparse relevance labels limit generalization; live Gemini accuracy has not been formally measured.
- Citation-ID validity does not establish semantic entailment; agents must review every suggested step.
- The shared admin key is not full production RBAC; the prototype uses one backend worker.
- Render Free cold starts can vary.

Production scale would require stronger authentication, scalable indexing/storage, monitoring, and privacy/governance controls.
