# Render deployment runbook

This runbook describes a prototype deployment from the `develop` branch. Do not
deploy real customer data or put credentials in Git, build commands, or chat.
The application uses two Python web services and one Render Postgres database.
The Streamlit service calls the public FastAPI HTTPS URL from its server process;
only FastAPI calls Gemini and Postgres.

## Configuration

| Resource | Setting | Value |
| --- | --- | --- |
| Postgres | Region | Same region as backend |
| Backend web service | Branch / root directory | `develop` / `backend` |
| Backend web service | Build command | `pip install -r requirements.txt` |
| Backend web service | Start command | `test -n "$DATABASE_URL" && python -m app.seed && exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1` |
| Backend web service | HTTP health check path | `/health` |
| Frontend web service | Branch / root directory | `develop` / repository root (leave root directory blank) |
| Frontend web service | Build command | `pip install -r frontend/requirements.txt` |
| Frontend web service | Start command | `python -m streamlit run frontend/app.py --server.address 0.0.0.0 --server.port "$PORT" --server.headless true` |

Use the Python runtime and set `PYTHON_VERSION=3.12.14` on both services. Do not
set `PORT` manually; Render supplies it. The frontend must run from the
repository root because `frontend/app.py` imports `frontend.api_client`.

The backend start command deliberately runs the idempotent seed every time its
single process starts. It inserts any missing synthetic seed IDs and leaves
existing records untouched, including records changed through ingestion. The
initial seed and later updates live in Postgres. The `test -n` guard makes the
hosted service fail to start if `DATABASE_URL` is absent, rather than silently
using a temporary SQLite database. Local commands still default to SQLite.
The SQLAlchemy schema and queries use portable constructs, and the automated
suite checks Postgres URL handling and dialect compilation. A live Postgres
transaction and restart check remain part of hosted validation.

## Environment variables

| Service | Name | Value or purpose |
| --- | --- | --- |
| Backend | `DATABASE_URL` | Render Postgres **internal** connection URL |
| Backend | `GEMINI_API_KEY` | Secret entered in the Render dashboard only |
| Backend | `GEMINI_MODEL` | Optional model override; otherwise the configured application default |
| Backend | `CORS_ORIGINS` | Exact frontend HTTPS origin, with no trailing slash |
| Backend | `ADMIN_API_KEY` | Optional secret; leave unset to disable admin updates |
| Backend | `PYTHON_VERSION` | `3.12.14` |
| Frontend | `API_BASE_URL` | Public backend HTTPS origin, with no trailing slash |
| Frontend | `PYTHON_VERSION` | `3.12.14` |

Keep backend and Postgres in the same Render region and use the internal URL
for the database. The Streamlit process uses the backend's public HTTPS URL;
it does not need a Postgres or Gemini credential. `CORS_ORIGINS` limits browser
origins, although Streamlit's server-side HTTP request is not a browser CORS
request. Do not set a wildcard origin. `GET /health` checks that the API
process responds; `GET /ready` additionally checks database access, search
indexes/model, and whether Gemini is configured. Readiness does **not** call
Gemini, so a hosted live request is still required.

## Durable and rebuildable state

Postgres durably stores tickets, KB articles, taxonomy, and versioned embedding
vectors. The backend's `backend/data/indexes/` FAISS files and
`backend/data/model_cache/` are disposable. On the first `/ready` or search
after a fresh deploy, the pinned ONNX MiniLM artifact may download; missing or
stale indexes rebuild from approved Postgres records and reuse stored vectors.
A persistent disk is not required for this small prototype. Model download,
FAISS construction, and service memory use must be checked on the chosen
Render instance. No paid compute plan is assumed by this runbook.

The previous PyTorch runtime's local Windows cold-start measurement was 11.6
seconds for API import. In the local ONNX prototype with a warm model cache,
peak process memory was 282.2 MiB through `/ready`, index rebuild, `/search`,
and a fake-provider `/resolve`. The hosted Linux memory peak and first model
download remain unverified.

Use one backend worker and one service instance for the prototype. The shared
in-process lock protects search/index updates and taxonomy reloads, and also
serializes Gemini calls within that worker. Additional processes would each
hold their own index and lock; horizontal scaling needs a coordinated indexing
design before it is safe.

## Hosted verification checklist

1. Confirm the backend deploy reaches Live. Check `/health` returns 200.
2. Call `/ready` and record whether it triggers a first model download or index
   rebuild. It should return 200 when the database, index, model, and Gemini
   configuration are available.
3. Confirm approved ticket and KB matches appear from `/search`. Restart the
   backend and confirm the same Postgres records remain and indexes rebuild.
4. Call `/analyze` and `/resolve` with the synthetic broadband example. Check
   cited IDs are among retrieved approved evidence and record response latency.
5. Open Streamlit, select the broadband example, and confirm analysis, ticket
   matches, KB matches, cited draft steps, and the agent-review warning.
6. Try an out-of-domain complaint for the insufficient-evidence state. The
   provider-error UI path is covered by local fake-provider tests; do not
   disable or alter hosted secrets solely to force that error. Review logs for
   request routing and failures without copying secret values or complaint
   text into reports.

The live example is: “My broadband drops every evening around 8 PM and I
already restarted the router twice.” Keep the result as a demonstration of a
single hosted run, not a measured production quality score.

## Security and operational limits

Admin routes return a configuration error when `ADMIN_API_KEY` is absent. A
shared admin key is suitable only for this controlled prototype; a production
service needs identity-based authentication, authorization, audit logs, rate
limiting, privacy and retention controls, and a stronger semantic grounding
check. The API deliberately avoids logging raw complaints and returns
sanitized provider/storage errors. Use Render environment settings for
credentials and avoid external database access unless it is needed for
administration. Confirm the selected Postgres plan's retention and backup
terms before treating it as durable beyond the demo window.
