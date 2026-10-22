# Phase 16: local semantic search

Use **Build semantic index**, then enter a natural-language query in **Explore by meaning**. The first build downloads data-only weights and tokenizer files for `minishlab/potion-base-8M` at pinned revision `bf8b056651a2c21b8d2565580b8569da283cab23`. Source is embedded locally with [Model2Vec](https://minish.ai/packages/model2vec/inference/); it is not sent to a hosted model. No API key is needed.

Units are modules, functions, classes, and methods, with path/name/signature context. Each unit's source is capped at 8,000 characters; results label this truncation. The repository cap is 10,000 units. This general-purpose static embedding model provides meaning-based ranking, not a code-trained reasoning model or correctness score. Cosine similarity is shown explicitly. Literal symbol search remains available separately.

Migration `004_semantic` adds a durable hash/model-keyed embedding cache. A changed file loses only its own cached units; unchanged unit embeddings are reused. Repository publication markers are invalidated during indexing. Build/update the semantic index after indexing a new commit; no stale source is served as current. Build failures roll back and release the shared indexing lock.

SQLite stores portable JSON vectors and ranks by exact cosine similarity. With the pgvector extension available, the migration enables it and adds native `vector(256)` storage; PostgreSQL ranks with exact cosine distance. Compose and PostgreSQL CI use the [official pgvector image](https://github.com/pgvector/pgvector#docker). Plain PostgreSQL without the extension retains the portable path. There is no approximate-nearest-neighbor index yet; benchmark before adding one.

API:

- `GET /repositories/{id}/semantic`: current readiness and document count.
- `POST /repositories/{id}/semantic`: build/update vectors; returns embedded/reused counts.
- `GET /repositories/{id}/semantic/search?q=...&limit=10`: ranked, commit-pinned source citations and symbol IDs.

Tests inject a deterministic provider to verify ranking, cache reuse, failure rollback, scope, and stale-index handling. PostgreSQL CI also checks native vector storage and retrieval. The real local model is verified separately in the browser; test providers are never used by application code.
