# Intelligent Support Ticket Resolution Assistant

This repository includes a FastAPI service, local data and semantic search,
Gemini complaint analysis, cited RAG resolution, controlled ingestion, and a
Streamlit support-agent frontend. Deployment is planned for a later phase.

## Run locally

Use Python 3.12 or a compatible Python 3 version. From the repository root:

```text
python -m venv .venv
```

If `python` is not on your `PATH`, use your installed Python executable for
this first command. Activate the environment:

```text
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS or Linux
source .venv/bin/activate
```

Then run:

```text
cd backend
python -m pip install -r requirements.txt
python -m app.seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/health` to see `{"status":"ok"}`.
In a second terminal, from the repository root with the same virtual
environment activated, run:

```text
python -m pip install -r frontend/requirements.txt
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501` for the agent page. It sends the complaint to
FastAPI's `/resolve` route and displays analysis, approved matches, a cited
resolution, and evidence status. It does not call Gemini directly. Set
`API_BASE_URL` in the frontend process environment to use a different backend;
the default is `http://127.0.0.1:8000`. For example, in PowerShell use
`$env:API_BASE_URL = "http://127.0.0.1:8000"` before starting Streamlit.
Run `python -m pytest -q` from `backend/` for backend tests, and
`python -m pytest -q frontend/tests` from the repository root for frontend
tests.

`APP_TITLE` is optional and changes the API title. `.env.example` lists the
available variables. The API reads environment variables and the ignored
repository-root `.env` file. Set `GEMINI_API_KEY` there for analysis and
resolution; never commit the real file.

## API routes

Seed the local database with `python -m app.seed` from `backend/`, then start
Uvicorn. `GET /health` checks the process; `GET /ready` checks the database,
search indexes/model, and Gemini configuration. The first readiness or search
request may load the embedding model and build indexes.

`POST /analyze` accepts `{"complaint":"..."}` and returns structured analysis
plus `latency_ms`. `POST /search` accepts the same complaint and optional
`top_k_tickets` and `top_k_kb` (1–20), returning approved evidence and scores.
`POST /resolve` runs analysis, retrieval, and cited RAG generation and returns
analysis, matches, resolution, source IDs, insufficient-evidence status, and
`latency_ms`. Similarity scores are ranking scores, not probabilities.

Optional `POST /admin/tickets`, `POST /admin/kb`, and `POST /admin/taxonomy`
reuse controlled ingestion. Set `ADMIN_API_KEY` in the environment and send it
as `X-Admin-Key`; without a configured key, these routes return 503. The CLI
remains available for local administration. `CORS_ORIGINS` accepts a
comma-separated list of explicit frontend origins; the default only allows
local Streamlit origins on port 8501.

Run `python -m app.api_smoke` from `backend/` for an HTTP smoke test using a
seeded temporary database and fake LLM, without consuming Gemini quota.

## Local data

From `backend/`, after installing its requirements:

```text
python -m app.seed
python -m evaluation.profile
```

The first command validates the synthetic seed files and creates
`backend/data/support.db` using SQLite. Running it again safely skips existing
records. The 12 seed case families expand to 120 stable ticket IDs, with 24
separate KB articles. The second command prints dataset counts and
missing-field counts. Seeding is insert-only in this phase; local seed edits
do not overwrite records already in the database.
An empty `resolution` on an open ticket is expected; resolved tickets must
have a resolution. The database file is local and ignored by Git.

The schema has four tables: `tickets`, `kb_articles`, `taxonomy_values`, and
`embeddings`. Only tickets that are both resolved and approved, and approved
KB articles, are returned by the repository's evidence-only queries. The
embedding table stores reusable, versioned vectors after index building. SQL is
isolated in `backend/app/storage.py`.

SQLite works without an external service. `DATABASE_URL` may override the
default database URL for development; leave it unset for the simplest setup.
Postgres driver and deployment configuration are planned for a later phase.

## Semantic search

From `backend/`, seed the local database first, then build the FAISS indexes:

```text
python -m app.seed
python -m app.build_indexes
python -m app.search_demo
```

The first index build downloads the pinned
`sentence-transformers/all-MiniLM-L6-v2` model for local CPU inference. Its
revision is set in `backend/app/config.py`. The model cache and generated
index files under `backend/data/` are ignored by Git. Normalized vectors are
also stored in the database, so missing or stale index files can be rebuilt
without embedding unchanged records again.

`search_demo` uses an evening broadband complaint by default. Try another:

```text
python -m app.search_demo --query "I cannot surf the web over cellular, but voice chat works." --tickets 3 --kb 3
```

The search returns separate ticket and KB matches with stable source IDs and
similarity scores. Scores rank results; they are not confidence probabilities.
Only resolved and approved tickets and approved KB articles are indexed.
Each returned match is checked against current approval status as well, so a
revoked source is not displayed while an index refresh is pending.
Set `SEARCH_TICKET_TOP_K` and `SEARCH_KB_TOP_K` to positive integers to change
the default result counts (5 each). Controlled Phase 6 ingestion refreshes the
indexes when searchable text or evidence eligibility changes.

## Updating support data

From the repository root, add or update one complete validated JSON record:

```text
python -m backend.app.ingest ticket path/to/ticket.json
python -m backend.app.ingest kb path/to/article.json
python -m backend.app.ingest taxonomy category satellite_backhaul --reviewed-by admin
```

Ticket IDs and KB IDs stay stable; updates keep their original `created_at` and
use a later timezone-aware `updated_at`. Changed KB guidance also increments
`version`. Only resolved, approved tickets and approved KB articles enter
retrieval. The ingestion command rebuilds small FAISS indexes when needed;
unchanged text reuses its durable embedding. New categories require an explicit
reviewed taxonomy command, then complaint analysis can use them on its next call.
Stored severity is `low`/`medium`/`high`/`critical`; stored sentiment is
`positive`/`neutral`/`frustrated`/`negative` (`ANGRY` maps to `negative`).

Run `python -m backend.app.evolving_demo` from the repository root to see an
unknown issue become a reviewed category and searchable ticket, including a
restart check. This demo uses a temporary database and a local embedding model;
it does not call Gemini.
