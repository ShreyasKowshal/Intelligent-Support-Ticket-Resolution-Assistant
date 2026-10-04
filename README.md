# Intelligent Support Ticket Resolution Assistant

## Project overview

An agent-facing telecom support assistant analyzes a customer complaint, finds semantically similar resolved tickets and
knowledge-base (KB) articles, and drafts cited resolution steps for **agent review**. It supports updated evidence and new
ticket classes. Semantic search helps find related issues that keyword search can miss.

## Architecture

```mermaid
flowchart LR
    A[Support Agent] --> B[Streamlit Frontend]
    B --> C[FastAPI Backend]
    C --> D[Gemini Complaint Analysis]
    D --> E{Actionable Telecom Issue?}
    E -- No --> F[Clarification Response]
    E -- Yes --> G[FastEmbed / ONNX MiniLM]
    G --> H1[FAISS Ticket Index]
    G --> H2[FAISS KB Index]
    H1 --> I[Similar Resolved Tickets]
    H2 --> J[Relevant KB Articles]
    I --> K[Gemini RAG]
    J --> K
    K --> L[Citation Validation]
    L --> M[Agent-Reviewed Resolution Draft]
    C --> N[(SQLite Local / Render Postgres)]
    N --> H1
    N --> H2
```

Non-actionable input stops before retrieval/RAG. The frontend calls FastAPI, not Gemini or the database.

## Complaint resolution flow

```mermaid
sequenceDiagram
    participant A as Support Agent
    participant F as Streamlit Frontend
    participant B as FastAPI Backend
    participant G as Gemini
    participant S as Semantic Search
    participant D as Database
    participant R as RAG / Citation Validation

    A->>F: Enter customer complaint
    F->>B: POST /resolve
    B->>G: Analyze complaint
    G-->>B: Intent, category, product, severity, sentiment
    B->>B: Check actionability

    alt Non-actionable input
        B-->>F: Clarification response
        F-->>A: Ask for a telecom service issue
    else Actionable telecom complaint
        B->>S: Search semantic evidence
        S->>D: Read approved tickets and KB
        D-->>S: Eligible evidence
        S-->>B: Similar tickets and KB articles
        B->>G: Generate draft from retrieved evidence
        G-->>B: Steps and source citations
        B->>R: Validate citation IDs
        R-->>B: Cited draft or insufficient evidence
        B-->>F: Analysis, matches, and resolution
        F-->>A: Display for agent review
    end
```

1. The support agent enters a complaint in Streamlit.
2. Streamlit sends it to FastAPI.
3. Gemini analyzes the complaint.
4. FastAPI checks whether the complaint is actionable.
5. Non-actionable input returns a clarification.
6. Actionable complaints are matched against approved tickets and KB articles.
7. Gemini drafts steps using retrieved evidence.
8. Citation validation checks source IDs.
9. The frontend displays the result for agent review.

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

## Requirements coverage

- **Architecture diagram:** included above.
- **Executable code:** FastAPI backend, Streamlit frontend, evaluation framework, and tests are checked into this repository; deployment instructions are included.
- **Additional exploration:** FAISS retrieval is compared with a TF-IDF baseline using held-out queries.
- **System-health evaluation:** `/health`, `/ready`, automated tests, and evaluation checks cover readiness and core system paths.
- **Production-scale considerations:** authentication, scalable retrieval/storage, monitoring, privacy/governance, cold starts, and worker limits are summarized under Limitations.
- **Dataset:** synthetic telecom support-ticket scenarios are used.

## Limitations

- Synthetic data and sparse relevance labels limit generalization; live Gemini accuracy has not been formally measured.
- Citation-ID validity does not establish semantic entailment; agents must review every suggested step.
- The shared admin key is not full production RBAC; the prototype uses one backend worker.
- Render Free cold starts can vary.

Production scale would require stronger authentication, scalable indexing/storage, monitoring, and privacy/governance controls.
