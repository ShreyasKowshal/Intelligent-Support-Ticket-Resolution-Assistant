# Code

## Summary

The repository contains a separated FastAPI/Python backend and React/TypeScript frontend, plus seed data, tests, and evaluation tooling.

## Repository Structure

```text
backend/
  app/          API and application modules
  data/seed/    synthetic tickets, KB articles, taxonomy
  evaluation/   runners, labels, and saved results
  tests/        backend tests
frontend-react/  Vite application and frontend tests
docs/           handoff and deployment docs
evaluation/     rubric documents
```

## Separation of Concerns

Backend routes and HTTP errors are in `backend/app/main.py`; contracts in `api_models.py`; analysis in `analysis.py`; actionability in `actionability.py`; retrieval in `search.py`; generation and citation checks in `rag.py`; persistence in `storage.py`; controlled updates in `ingestion.py`; settings in `config.py`.

The React app separates components, an API service, response types, a backend-status hook, and display utilities under `frontend-react/src/`.

## Validation and Error Handling

Pydantic checks request and record shapes, including the 3000-character complaint limit. Gemini analysis and resolution are validated before the API responds. Non-actionable complaints skip retrieval/RAG; insufficient evidence yields no invented steps. API errors use safe messages, and the frontend handles loading, retry, and error states.

## Security / Configuration

Backend secrets use environment variables; `.env` is ignored and no credential is tracked. `VITE_API_BASE_URL` is a public API origin, not a secret. Admin routes require `ADMIN_API_KEY` when enabled, and CORS permits explicit origins. Request logging omits complaint text.

## Tests and Build

The latest verified run passed **241 backend tests** and **20 frontend tests**. TypeScript checking and the Vite production build passed. These are test counts, not a coverage percentage.

## Executable Code

Full backend and frontend source is on `main`. `README.md` gives local setup; `backend/app/seed.py` and `backend/evaluation/` provide repeatable data and evaluation commands; `docs/RENDER_DEPLOYMENT.md` records hosted settings.

## Strengths

Typed contracts, module boundaries, validation, deterministic evaluation, and a reusable storage layer make the prototype inspectable.

## Limitations / Production Gaps

The deployment uses one worker with process-local search state. Citation checks are structural, and the project does not implement full enterprise authorization or observability.

## Repository Evidence

- [backend/app/](../backend/app/), [backend/tests/](../backend/tests/), [backend/evaluation/](../backend/evaluation/), and [backend/data/seed/](../backend/data/seed/).
- [frontend-react/src/](../frontend-react/src/), [frontend-react/package.json](../frontend-react/package.json), and [frontend-react/package-lock.json](../frontend-react/package-lock.json).
- [README.md](../README.md), [.gitignore](../.gitignore), and [docs/RENDER_DEPLOYMENT.md](../docs/RENDER_DEPLOYMENT.md).
