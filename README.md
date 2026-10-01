# Intelligent Support Ticket Resolution Assistant

This repository currently includes the Phase 1 FastAPI foundation and the
Phase 2 local data foundation. Semantic search, complaint analysis, RAG, and
the frontend will be added in later phases.

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
embedding table is empty for now. SQL is isolated in `backend/app/storage.py`.

SQLite works without an external service. `DATABASE_URL` may override the
default database URL for development; leave it unset for the simplest setup.
Postgres driver and deployment configuration are planned for a later phase.
