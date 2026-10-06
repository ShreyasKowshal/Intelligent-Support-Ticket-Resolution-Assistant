# Design Decisions

## Summary

The design keeps the agent UI, API, structured analysis, retrieval, storage, and generation separate so each can be tested and changed independently.

## Frontend

React provides a structured support workspace; TypeScript types the API responses; Tailwind styles responsive cards and states; Vite produces a static production build. The browser calls FastAPI rather than Gemini or the database.

## Backend

FastAPI and Python fit the ML/LLM libraries while Pydantic schemas validate requests, records, and responses. Routes delegate work to analysis, actionability, search, RAG, and ingestion modules.

## Gemini

Gemini provides structured complaint analysis and generates a draft conditioned on retrieved evidence. It does **not** perform vector search.

## MiniLM and FastEmbed / ONNX

The pinned MiniLM sentence encoder produces 384-dimensional vectors for semantic matching. FastEmbed/ONNX avoids a PyTorch runtime in the hosted CPU deployment. The repository does not include a controlled before/after memory benchmark.

## FAISS

Each evidence type uses `IndexFlatIP`. Vectors are normalized, so inner-product scores rank results like cosine similarity; scores are not calibrated probabilities.

## Separate Ticket and KB Indexes

Tickets and KB articles have different searchable fields and are shown separately. Ticket embeddings use complaint, product, and category; KB embeddings use title, content, and category. Historical ticket resolution text is excluded from matching but supplied later as generation evidence.

## Data Storage

SQLAlchemy supports simple local SQLite setup and hosted PostgreSQL configuration. Source records and embedding metadata persist in the database; FAISS index files can be rebuilt.

## Citation Validation

Generated step IDs must belong to retrieved evidence. The validator enforces source-ID validity and cited steps, but it does not prove semantic entailment or guarantee KB precedence when sources conflict.

## Controlled Ingestion

Only resolved, approved tickets and approved KB articles become retrieval evidence. Guarded admin updates and reviewed taxonomy additions avoid automatically treating raw complaints or AI drafts as trusted records.

## One Worker

The documented Render command uses one worker because the prototype keeps mutable FAISS state in-process. This avoids cross-worker index coordination but constrains throughput.

## Strengths

The searchable text, eligibility rules, and source-ID checks are explicit and independently testable.

## Limitations / Production Gaps

Larger deployments would need shared index coordination, stronger admin identity and audit controls, and verification of the meaning of cited advice.

## Repository Evidence

- [frontend-react/package.json](../../frontend-react/package.json), [frontend-react/src/](../../frontend-react/src/), and [frontend-react/vite.config.ts](../../frontend-react/vite.config.ts).
- [backend/app/analysis.py](../../backend/app/analysis.py), [backend/app/gemini_client.py](../../backend/app/gemini_client.py), and [backend/app/main.py](../../backend/app/main.py).
- [backend/app/config.py](../../backend/app/config.py), [backend/app/search.py](../../backend/app/search.py), [backend/app/rag.py](../../backend/app/rag.py), [backend/app/storage.py](../../backend/app/storage.py), and [backend/app/ingestion.py](../../backend/app/ingestion.py).
- [docs/RENDER_DEPLOYMENT.md](../RENDER_DEPLOYMENT.md) and [backend/evaluation/results/evaluation_summary.md](../../backend/evaluation/results/evaluation_summary.md).
