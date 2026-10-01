# Intelligent Support Ticket Resolution Assistant

This repository currently includes the FastAPI foundation, local data, and
semantic search. Complaint analysis, RAG, and the frontend will be added in
later phases.

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
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` to see `{"status":"ok"}`.
Run `python -m pytest` from `backend/` to execute the test.

`APP_TITLE` is optional and changes the API title. `.env.example` lists the
available variables. The application uses environment variables directly and
does not require a `.env` file.

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
the default result counts (5 each). Run `python -m app.build_indexes` after
approved source records change; Phase 6 will connect this refresh to ingestion.
