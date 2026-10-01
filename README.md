# Intelligent Support Ticket Resolution Assistant

This repository is at Phase 1: a minimal FastAPI foundation. Ticket data,
semantic search, complaint analysis, RAG, and the frontend will be added in
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
available variable. The application uses environment variables directly and
does not require a `.env` file.
