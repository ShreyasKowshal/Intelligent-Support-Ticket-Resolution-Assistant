# Render deployment

## Services

- Frontend: https://support-ticket-assistant.onrender.com
- Backend: https://support-ticket-assistant-api.onrender.com
- Frontend branch: `develop` for current hosted testing; `main` remains unchanged
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
  - `CORS_ORIGINS`: include `https://support-ticket-assistant.onrender.com` alongside any existing allowed origins
- Optional environment variables:
  - `GEMINI_MODEL`: Gemini model override
  - `ADMIN_API_KEY`: enables guarded admin routes when set
- `GET /health`: process liveness
- `GET /ready`: database, search index, embedding model, and Gemini configuration readiness

## Frontend

- Type: Render Static Site
- Branch: `develop`
- Root directory: `frontend-react`
- Build command: `npm install && npm run build`
- Publish directory: `dist`
- `VITE_API_BASE_URL`: `https://support-ticket-assistant-api.onrender.com` (public backend origin; no trailing slash)
- No SPA rewrite is needed because the app has no client-side routes.

## Cold start

Render Free services can spin down when idle. React checks backend health and
readiness every five seconds for up to 180 seconds. **Retry backend connection**
starts a fresh attempt. Startup time can still vary.

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
