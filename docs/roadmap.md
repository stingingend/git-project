# Build roadmap

Each milestone should work on its own and include a focused check.

| Step | Goal | What to understand |
| --- | --- | --- |
| 1 | API skeleton and health endpoint | HTTP routes, JSON, and API tests |
| 2 | Persist repository metadata | Tables, sessions, and transactions |
| 3 | Ingest a public GitHub repository | URL validation, shallow clones, discovery, and limits |
| 4 | Parse Python symbols with Tree-sitter | Syntax trees, scopes, and source ranges |
| 5 | Store and query the index | Files, symbols, statistics, and atomic indexing |
| 6 | Build a minimal repository UI | React state, requests, loading, and errors |
| 7 | Search symbols and navigate source | Filtering, identifiers, and source highlighting |
| 8 | Resolve structural relationships | Containment, imports, and directed graphs |
| 9 | Add PostgreSQL, Docker, and CI | Persistent storage and repeatable checks |

Later: dependency visualization, approximate call resolution, background indexing jobs, and incremental indexing. Semantic search and cited Q&A come after the structural index works reliably.
