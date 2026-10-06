# Solution Depth and Production Scale Considerations

## Summary

This is an end-to-end, agent-reviewed prototype: it combines structured analysis, approved evidence retrieval, cited drafting, and controlled evidence updates. It is suitable for evaluation, with production limits stated below.

## End-to-End Solution Flow

Support agent → React frontend → FastAPI → Gemini complaint analysis → actionability check → MiniLM query embedding → separate FAISS ticket and KB retrieval → Gemini RAG → citation validation → agent-reviewed resolution.

## Requirement Coverage

The API returns intent/category, product, severity, and sentiment. Search uses only resolved and approved tickets and approved KB articles. RAG supplies numbered steps with source IDs; weak evidence can produce an insufficient-evidence response. Non-actionable input receives clarification without retrieval or RAG.

The synthetic seed contains 120 tickets and 24 KB articles; 96 resolved, approved tickets and 22 approved KB articles are eligible for retrieval.

## Evolving Data and Ticket Classes

A new complaint is not saved automatically. After a case is resolved and reviewed, an authorized operator can manually add it as a resolved, approved ticket through backend ingestion or the guarded admin route.

Changes to searchable text of eligible records or to evidence eligibility refresh the indexes; new eligible records receive embeddings. Reviewed taxonomy values can also be added. Records and embedding metadata persist in the database; missing or stale FAISS files can be rebuilt after restart. Adding evidence or taxonomy values does not require full model retraining.

## Current Production-Oriented Features

FastAPI validates requests, returns sanitized errors, and logs route/status/latency without complaint text. CORS uses explicit origins. Backend credentials and database settings come from environment variables. The Render guide specifies PostgreSQL, one API worker, and separate React Static Site deployment. Health/readiness endpoints, guarded admin routes, evidence approval, and agent review support controlled use.

## Strengths

The evidence lifecycle prevents raw complaints and unapproved records from entering retrieval, while the React UI keeps source inspection available to the agent.

## Limitations / Production Gaps

One worker and process-local FAISS state limit concurrency and horizontal scaling. A shared admin key is not RBAC; full rate limiting, actor-level audit trails, centralized monitoring, and comprehensive privacy/PII governance are not implemented. Render Free cold starts vary. The corpus is synthetic, live Gemini quality is not formally benchmarked, and valid citation IDs do not prove that a step is semantically supported.

At larger scale, this design would need stronger authentication, rate limiting, actor-level audit logs, centralized metrics and alerts, privacy controls, shared/scalable vector infrastructure, multi-worker-safe updates, provider retries/circuit breakers, and stronger grounding verification.

## Repository Evidence

- [README.md](../../README.md) and [docs/RENDER_DEPLOYMENT.md](../RENDER_DEPLOYMENT.md) — architecture, deployment, and limitations.
- [backend/app/api_service.py](../../backend/app/api_service.py), [backend/app/main.py](../../backend/app/main.py), and [backend/app/config.py](../../backend/app/config.py) — workflow, routes, readiness, errors, logging, and CORS.
- [backend/app/ingestion.py](../../backend/app/ingestion.py), [backend/app/storage.py](../../backend/app/storage.py), and [backend/app/search.py](../../backend/app/search.py) — approved data lifecycle and index rebuild.
- [backend/app/rag.py](../../backend/app/rag.py) and [backend/evaluation/results/evaluation_summary.md](../../backend/evaluation/results/evaluation_summary.md) — generation guardrails and their limits.
