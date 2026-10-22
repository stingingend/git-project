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
| 13 — complete | Index changes incrementally | File hashes, changed source, and stable index records |
| 14 — complete | Introduce database migrations | Versioned schemas, upgrades, and preserving existing indexes |
| 15 — complete | Broaden approximate call resolution | Imports, receiver context, and invalidation |
| 16 — complete | Add semantic symbol search | Local embeddings, storage, and ranked retrieval |
| 17 — complete | Answer questions with source citations | Retrieval, graph context, and optional generation |
| 18 — complete | Analyze change impact | Reverse dependencies and affected definitions |
| 19 — complete | Analyze public pull requests | Changed lines, impacted symbols, and signed webhooks |
| 20 — complete | Measure architecture | Cycles, fan-in/out, centrality, and coupling |
| 21 — complete | Benchmark and prepare deployment | Measured performance, operational checks, and release docs |

Private repositories and PR comment publishing remain product extensions. Cloud deployment and optional webhook/model activation need account/configuration setup; public read-only PR reports work independently.
