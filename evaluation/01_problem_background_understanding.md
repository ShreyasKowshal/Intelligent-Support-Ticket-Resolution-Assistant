# Problem Background Understanding

## Summary

Telecom support agents search past tickets and knowledge-base (KB) articles to resolve customer complaints. Keyword search can miss relevant cases when customers describe the same fault in different words. This assistant helps an agent find related evidence and review a drafted resolution.

## Problem Being Solved

“My broadband drops every evening” and “My internet disconnects at night” may describe the same recurring fault without sharing the most useful search terms. Semantic retrieval ranks related complaints by meaning, then presents resolved tickets and KB guidance that an agent can inspect.

## Intended User

The user is a support agent who enters a customer's complaint. The generated steps are a draft for agent review before use with the customer; the customer does not operate this interface.

## Mapping to the Use Case

1. **Complaint parsing:** Gemini returns intent, category, product, severity, and sentiment in a validated structure.
2. **Semantic retrieval and RAG:** MiniLM embeddings and FAISS retrieve approved historical evidence; Gemini drafts cited steps from that evidence.
3. **Evolving data and classes:** Guarded ingestion accepts reviewed tickets, KB articles, and taxonomy additions, with index refresh.

## Repository Evidence

- [README.md](../README.md) — problem statement, architecture, and agent workflow.
- [backend/app/analysis.py](../backend/app/analysis.py) — structured complaint analysis.
- [backend/app/search.py](../backend/app/search.py) and [backend/app/rag.py](../backend/app/rag.py) — retrieval and cited drafting.
- [backend/app/ingestion.py](../backend/app/ingestion.py) and [backend/app/main.py](../backend/app/main.py) — controlled updates and API routes.
- [frontend-react/](../frontend-react/) — agent-facing interface.

## Strengths

The workflow directly addresses the wording gap in keyword search and keeps the agent responsible for the final advice.
