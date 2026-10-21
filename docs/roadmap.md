# Build roadmap

Each milestone should work on its own and include a focused check.

| Step | Goal | What to understand |
| --- | --- | --- |
| 1 — complete | API skeleton and health endpoint | HTTP routes, JSON, and API tests |
| 2 — complete | Persist repository metadata | Tables, sessions, and transactions |
| 3 — complete | Ingest a public GitHub repository | URL validation, shallow clones, discovery, and limits |
| 4 — complete | Parse Python symbols with Tree-sitter | Syntax trees, scopes, and source ranges |
| 5 — complete | Store and query the index | Files, symbols, statistics, and atomic indexing |
| 6 — complete | Build a minimal repository UI | React state, requests, loading, and errors |
| 7 — complete | Search symbols and navigate source | Filtering, identifiers, and source highlighting |
| 8 — complete | Resolve structural relationships | Containment, imports, and directed graphs |
| 9 — complete | Add PostgreSQL, Docker, and CI | Persistent storage and repeatable checks |
| 10 — complete | Visualize file dependencies | Directed edges, bounded neighborhoods, and graph navigation |
| 11 — complete | Inspect approximate call sites | Syntax traversal, lexical candidates, uncertainty, and source navigation |
| 12 — complete | Run indexing in background jobs | Job lifecycle, progress polling, and recovery |
| 13 | Index changes incrementally | File hashes, changed source, and stable index records |

Later: broader call resolution and schema migrations. Semantic search and cited Q&A come after the structural index works reliably.
