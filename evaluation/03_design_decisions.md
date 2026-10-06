# Design Decisions

## Summary

The project separates the frontend, backend, LLM analysis and generation, semantic retrieval, storage, and validation. Each responsibility has a clear role and can be tested independently.

## React

### What it does in this project

React provides the support-agent interface. The agent enters a customer complaint and sees its analysis, similar resolved tickets, relevant KB articles, generated resolution steps, and citations. The interface also shows clarification, insufficient-evidence, and backend status states.

### Why I used it

Components keep this interactive workflow structured and maintainable. React separates the interface from the FastAPI backend and can be deployed as a Render Static Site.

## TypeScript

### What it does in this project

TypeScript defines frontend types for API responses, complaint analysis, retrieved evidence, and resolution data.

### Why I used it

Types catch mismatches earlier, make the React-to-API integration safer, and make the interface easier to maintain.

## Tailwind CSS

### What it does in this project

Tailwind styles the agent workspace, cards, responsive layout, status states, and evidence sections.

### Why I used it

Utility classes make styling consistent and responsive without maintaining a large custom CSS file.

## Vite

### What it does in this project

Vite runs the React development environment and creates the production dist build published by Render.

### Why I used it

It provides fast React and TypeScript development tooling and a simple static production build.

## FastAPI

### What it does in this project

FastAPI exposes complaint analysis, search, resolution, health/readiness, and guarded admin ingestion routes. The backend coordinates Gemini, actionability checks, FAISS retrieval, RAG, database operations, and validation.

### Why I used it

The Python backend integrates with the project's ML, LLM, and vector-search libraries. FastAPI and Pydantic provide typed request/response validation and a clear API boundary for React.

## Gemini

### What it does in this project

Gemini has two roles. First, it produces structured complaint analysis covering intent/category, product, severity, and sentiment. Second, it receives the complaint and retrieved evidence to draft step-by-step resolution guidance with citations. Gemini does not perform vector similarity search.

### Why I used it

It supports natural-language analysis with structured output and generation conditioned on supplied evidence. The repository does not formally benchmark live Gemini accuracy.

## MiniLM (all-MiniLM-L6-v2)

### What it does in this project

MiniLM converts complaint queries and searchable ticket/KB text into 384-dimensional embeddings. The query embedding is compared with embeddings for stored evidence to find semantically similar records.

### Why I used it

It is a compact sentence embedding model suited to semantic similarity and CPU deployment. Its 384-dimensional vectors have lower storage and search cost than much larger embeddings.

## FastEmbed / ONNX

### What it does in this project

FastEmbed runs the ONNX MiniLM model to produce embeddings without a PyTorch runtime.

### Why I used it

Avoiding PyTorch keeps the CPU embedding pipeline lighter for Render's memory constraints. The repository does not contain a controlled PyTorch-versus-ONNX memory benchmark, so no exact improvement is claimed.

## FAISS

### What it does in this project

FAISS searches ticket and KB embedding vectors for evidence similar to the complaint query. The indexes use IndexFlatIP. Vectors are normalized before indexing and querying, so inner-product ranking behaves like cosine-similarity ranking.

### Why I used it

FAISS provides vector similarity search that works with the MiniLM embeddings. Exact flat search is straightforward for the current small dataset.

## Separate Ticket and KB FAISS Indexes

### What they do in this project

One index searches eligible resolved tickets; another searches eligible KB articles. Ticket searchable text combines complaint, product, and category. KB searchable text combines title, content, and category. Results retain their distinct evidence types and source IDs.

### Why I used separate indexes

Tickets and KB articles have different structures and purposes. Separate indexes keep their searchable fields, result mappings, filtering, ranking, and presentation clear.

## Why Ticket Resolution Text Is Not Embedded

### What happens in this project

Historical resolution text is excluded from ticket search embeddings. Ticket matching uses complaint, product, and category. After retrieval, the historical resolution is supplied to Gemini as generation evidence.

### Why I designed it this way

The incoming query describes a problem, so retrieval should find similar problems rather than match solution wording. Historical solutions are still available when the draft is generated.

## SQLAlchemy

### What it does in this project

SQLAlchemy provides the database and repository abstraction used with local SQLite and hosted PostgreSQL.

### Why I used it

It isolates database-specific details and avoids maintaining separate application flows for each database.

## SQLite

### What it does in this project

SQLite is the default local development database.

### Why I used it

It is lightweight and needs no separate database server for local setup.

## PostgreSQL

### What it does in this project

Render PostgreSQL provides durable hosted storage for tickets, KB articles, taxonomy values, and embedding metadata.

### Why I used it

It is more suitable than SQLite for persistent hosted use and is available as a managed Render service.

## Citation Validation

### What it does in this project

The backend checks generated citation IDs against the evidence actually retrieved. It requires cited resolution steps and rejects IDs that were not retrieved.

### Why I used it

This prevents invented source IDs and gives the agent traceable references. A valid citation ID does not prove that the cited source semantically supports the advice.

## Controlled Evidence Approval / Ingestion

### What it does in this project

Guarded backend admin ingestion can add resolved tickets, KB articles, and reviewed taxonomy values. Only eligible approved evidence enters retrieval; indexes refresh when eligible searchable data changes.

### Why I used it

Raw complaints and AI drafts do not automatically become trusted evidence. A complaint can be resolved and reviewed, then manually added as approved evidence for future retrieval. This lets data and ticket classes evolve without full model retraining.

## One Backend Worker

### What it does in this project

The documented Render backend command runs one Uvicorn worker.

### Why I used it

FAISS indexes and mutable search state are process-local in this prototype. One worker avoids synchronization inconsistencies between separate process copies, but limits throughput. Horizontal scaling would require shared or coordinated search infrastructure.

## Agent Review

### What it does in this project

The generated resolution is shown as a draft for a support agent to review before using it with a customer.

### Why I designed it this way

Citation validation checks structure, not full semantic support, and Gemini can still give incorrect advice. Human review is an intentional safeguard.

## Quick Design Decision Summary

| Technology / Decision | What it does in my project | Why I used it |
| --- | --- | --- |
| React | Agent complaint and resolution interface | Structured interactive workflow |
| TypeScript | Types API and result data | Earlier type checks |
| Tailwind | Styles cards, states, and layouts | Consistent responsive styling |
| Vite | Runs development and builds dist | Simple static build tooling |
| FastAPI | Exposes and coordinates backend routes | Python ML integration and validation |
| Gemini | Analyzes complaints and drafts cited steps | Structured analysis and grounded generation |
| MiniLM | Produces 384-dimensional embeddings | Compact semantic matching |
| FastEmbed/ONNX | Runs the embedding model | CPU-friendly runtime without PyTorch |
| FAISS | Searches normalized vectors | Straightforward exact similarity search |
| Separate ticket/KB indexes | Searches evidence types separately | Clear fields, mappings, and results |
| SQLAlchemy | Abstracts local and hosted storage | Shared database access layer |
| SQLite | Stores local development data | Setup without a database server |
| PostgreSQL | Stores hosted persistent data | Managed durable database |
| Citation validation | Checks cited IDs and steps | Traceable sources, fewer invented IDs |
| Controlled ingestion | Gates new evidence and classes | Prevents unreviewed retrieval data |
| One worker | Keeps one process-local search state | Avoids cross-worker index drift |
| Agent review | Requires review of the generated draft | Catches unsupported or incorrect advice |

## Strengths

The design separates generation from retrieval, restricts retrieval to approved evidence, keeps source IDs traceable, and treats the output as an agent-reviewed draft. Searchable text and index lifecycle rules are explicit and testable.

## Limitations / Production Gaps

Search state is process-local, and one worker limits throughput. Admin access uses a shared key rather than full RBAC. Citation checks do not guarantee semantic support. Enterprise deployment would need stronger observability and coordinated scaling.

## Repository Evidence

- [frontend-react/package.json](../frontend-react/package.json), [frontend-react/src/](../frontend-react/src/), and [frontend-react/vite.config.ts](../frontend-react/vite.config.ts).
- [backend/app/analysis.py](../backend/app/analysis.py), [backend/app/gemini_client.py](../backend/app/gemini_client.py), and [backend/app/main.py](../backend/app/main.py).
- [backend/app/config.py](../backend/app/config.py), [backend/app/search.py](../backend/app/search.py), [backend/app/rag.py](../backend/app/rag.py), [backend/app/storage.py](../backend/app/storage.py), and [backend/app/ingestion.py](../backend/app/ingestion.py).
- [docs/RENDER_DEPLOYMENT.md](../docs/RENDER_DEPLOYMENT.md) and [backend/evaluation/results/evaluation_summary.md](../backend/evaluation/results/evaluation_summary.md).
