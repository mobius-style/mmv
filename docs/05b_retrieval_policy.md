# 05b Retrieval Policy

## Principle
Retrieval is subordinate to route decision. It exists to support `verify`, not to become the default runtime mode.

## Chat and embedding separation
The chat model is fixed to `Phi-4-mini-flash-reasoning`.
Embedding must use a separate lightweight model.

## MMV retrieval profile
- simple chunking
- lightweight embeddings
- top-k retrieval
- source attribution
- no reranker
- no graph RAG
- no always-on retrieval

## Suggested MMV defaults
- chunk size: 600-900 chars
- chunk overlap: 80-120 chars
- top_k: 4
- score threshold: provider-specific, start conservative

## Web verification policy
Use web verification only when:
- recency matters
- the user requests current/public facts
- local corpus is insufficient

## Non-goals
- enterprise search
- long-horizon knowledge sync
- provider-specific web ranking optimization
