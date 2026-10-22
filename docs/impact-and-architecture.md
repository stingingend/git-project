# Phases 18 and 20: impact and architecture

Open **Impact & architecture** below the semantic tools. Choose a file, or select a symbol in the source explorer and analyze that symbol. Reports trace reverse imports and approximate call candidates, including test files where they depend on the selected source. Depth is bounded (default six, maximum twelve); visited symbols are capped at 5,000 and displayed results at 100 by default. Reached limits are explicit. Every report is tied to a published commit.

Impact scope describes dependent-file counts: small under five, medium five through nineteen, broad twenty or more. It is not a breakage probability. Unresolved imports, ambiguous calls, syntax recovery, dynamic Python behavior, and external consumers can hide impact. New files absent from the index cannot have known reverse edges yet.

The architecture view computes unique directed import pairs, fan-in/out, isolated files, strongly connected cycle components, and PageRank centrality (30 iterations, damping 0.85, with dangling-node redistribution). Cycle groups are sets, not an ordered edge-by-edge cycle. Hub tables show up to fifty files. Source links navigate the existing file explorer.

Review hotspots combine coupling with syntax branch points: `(fan-in + fan-out + 1) × (branch points + 1)`. Branch points count Tree-sitter conditional, loop, exception, boolean, and match-case nodes. This is a review-priority proxy, not measured cyclomatic complexity or runtime risk. Files with syntax errors have no branch score. Git change frequency is not inferred from a shallow clone.

API:

- `POST /repositories/{id}/impact`: `file_ids`, `symbol_ids`, optional `max_depth` and `limit`.
- `GET /repositories/{id}/architecture`: cycle groups, hubs, review hotspots, and import roots.

Neither feature needs embeddings or an LLM. Tests use known cyclic imports and explicit call chains to check exact affected sets, test dependents, isolation, centrality normalization, and traversal truncation.
