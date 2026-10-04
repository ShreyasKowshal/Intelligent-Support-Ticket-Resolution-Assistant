# Render deployment

## Services

- Frontend: https://support-ticket-assistant-ui.onrender.com
- Backend: https://support-ticket-assistant-api.onrender.com
- Branch: `develop`
- Hosted database: Render Postgres
- Local fallback: SQLite

## Backend

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `test -n "$DATABASE_URL" && python -m app.seed && exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1`
- Required environment variables:
  - `DATABASE_URL`: Render Postgres internal connection URL
  - `GEMINI_API_KEY`: configure as a secret in Render
  - `PYTHON_VERSION`: `3.12.14`
- Optional environment variables:
  - `GEMINI_MODEL`: Gemini model override
  - `ADMIN_API_KEY`: enables guarded admin routes when set
- `GET /health`: process liveness
- `GET /ready`: database, search index, embedding model, and Gemini configuration readiness

## Frontend

- Root directory: repository root (leave Render's Root Directory field blank)
- Build command: `pip install -r frontend/requirements.txt`
- Start command: `python -m streamlit run frontend/app.py --server.address 0.0.0.0 --server.port "$PORT" --server.headless true`
- `API_BASE_URL`: `https://support-ticket-assistant-api.onrender.com` (no trailing slash)
- `PYTHON_VERSION`: `3.12.14`

## Cold start

Render Free can sleep. The browser makes wake attempts at 0, 25, and 75
seconds; readiness polls about every 5 seconds within a 180-second startup
window. **Retry backend connection** starts a fresh attempt. The latest
sleeping-backend, frontend-only wake test worked, but startup time can still
vary on Render Free.

## Quick verification

1. Check backend `GET /health`.
2. Check backend `GET /ready`.
3. Open the frontend URL.
4. Submit: “My broadband drops every evening around 8 PM and I already restarted the router twice.”
5. Confirm analysis, ticket and KB retrieval, cited resolution, and source IDs appear.

## Limitations

- Render Free cold starts can vary.
- The prototype uses one backend worker.
- Admin security suits controlled evaluation, not full production RBAC.
