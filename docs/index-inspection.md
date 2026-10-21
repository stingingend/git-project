# Milestone 5: inspect the saved index

The previous stages collected files and extracted symbols. This milestone makes that data easier to inspect, and gives the next frontend milestone three read operations to build on.

## Repository overview

`GET /repositories/{id}/overview` combines three existing records:

```text
repository → URL, owner, name, status, creation time
snapshot   → commit, branch, ingestion time, files, lines, skipped files
parsing    → parse time, functions, methods, classes, imports, error counts
```

The query uses outer joins because a registered repository may not have a source snapshot or parse result yet. Those sections return `null` when unavailable. This lets a client distinguish “not parsed” from “parsed with zero functions.”

The summary counts already belong to the stored snapshots. A GET request does not recompute them or contact GitHub.

## File inspection

`GET /repositories/{id}/files/{file_id}` returns the source snapshot together with its file metadata, parse status, commit link, and one page of symbols.

The embedded symbol page contains `items`, `total`, `limit`, and `offset`. A file can contain many definitions, so the response defaults to 100 symbols and caps the requested page size at 500. Source itself is bounded by the ingestion milestone's 1 MB per-file limit.

Before parsing, the `parsing` section and symbol `total` are `null`. After parsing, an empty file has a total of zero. A file with malformed syntax carries the parser's error flag alongside any recovered definitions.

## Symbol inspection

`GET /repositories/{id}/symbols/{symbol_id}` returns a symbol, its file metadata, the source lines it covers, and a GitHub link such as:

```text
https://github.com/owner/repository/blob/COMMIT/path.py#L3-L8
```

The path is URL-encoded, while the commit hash fixes the target to the source that was actually ingested. Using a branch name would let the target move when someone pushes new code.

Line numbers are 1-based and inclusive. The snippet comes from saved source and preserves indentation. It omits the LF after the last selected line. Splitting on LF matches Tree-sitter's line boundaries, including when a Python string contains a Unicode separator that `str.splitlines()` would otherwise treat as another line.

## Repository boundaries and stale IDs

Every detail query checks the repository ID along with the requested file or symbol. A valid ID from another repository returns `404`; it does not reveal that repository's source.

IDs identify current database records. Re-ingestion replaces files and invalidates parsed results; re-parsing replaces symbol records. A client should reload lists after either operation rather than treating these IDs as permanent links. Commit-pinned GitHub URLs provide the external source reference.

## Read consistency

Writers still replace source and parse results in transactions. The new SQLite inspection endpoints also explicitly begin a read transaction, so a concurrent write cannot make one file response mix old source with a newer set of symbols. The read session closes at the end of the request. This is separate from the processing lock used by ingestion and parsing.

The overview reads its related records in one joined query. File and symbol responses select only the current repository's data; file inspection then reads its bounded symbol page within the same transaction.

## Code organization

- `index.py`: queries and source-link/snippet construction.
- `schemas.py`: explicit response shapes, including nullable stage metadata.
- `main.py`: endpoint parameters, response schemas, read sessions, and `404` handling.

No new tables or columns are needed. Existing ingestion and parsing endpoints remain available.

## What is tested?

Tests cover registered, ingested, and parsed overviews; exact source and snippets; symbol paging; empty files; syntax-error flags; encoded paths; repository boundaries; application restart; and a write committed between the two file-inspection queries. That last case checks the read transaction's behavior with SQLite WAL enabled in the test database.

## Next milestone

A minimal Next.js frontend can submit a URL, run ingestion and parsing, show the overview, list files, and inspect their saved source. Search and graph features will follow in their own milestones.
