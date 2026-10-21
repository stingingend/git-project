# Milestone 7: symbol search and source navigation

The web interface could browse files. This milestone adds repository-wide lookup and a direct path from a definition to its saved source.

## Follow a search

```text
Type a term and choose an optional symbol type
    → wait for a short pause in typing
    → GET /repositories/{id}/search
    → count and page matching stored symbols
    → choose a result
    → validate its current identity and commit
    → load its saved file
    → select the source page and highlight the definition
```

Searching does not contact GitHub or re-run Tree-sitter. It queries the symbol records produced by the earlier parsing stage.

## Matching and ordering

The backend joins symbols to their source files and searches names, qualified names, signatures, and file paths. A type filter restricts results to functions, classes, methods, or imports.

This is literal substring search. SQL wildcard characters are escaped, so a `%` in a signature or an underscore in a name has its ordinary meaning. SQLite's default case-insensitive matching covers ASCII; this milestone does not implement full Unicode case folding or semantic search.

Exact names rank first, then name prefixes, then other matches. File path, start line, and symbol ID break ties deterministically. Repeated overload definitions can appear as separate results with distinct source ranges.

## Paging and provenance

The response contains `total`, `limit`, `offset`, `items`, `parsed`, and `commit_sha`. Each item combines a symbol with its file path and syntax-error flag. Count and item queries use the inspection read transaction, keeping the page internally consistent on SQLite.

The UI requests 20 results at a time; the API caps requested page size at 100. No term means no browser request. An existing unparsed repository returns an empty page with `parsed: false`, distinguishing unavailable extraction from a completed search with no matches.

## Why debounce and ignore old responses?

Typing a word can generate many intermediate terms. The search component waits 200 ms after a change before sending a request. Query, filter, and page changes cancel the pending timer. Its effect cleanup also ignores a response that arrives after the user has moved on.

Changing repositories or refreshing the index resets the search component. The source loader has a separate request counter so a slower earlier click cannot replace a later selection.

## Selection and stale IDs

A search result contains a symbol ID, but IDs alone are not durable: re-parsing replaces symbol records. The navigation helper first fetches symbol detail and checks the commit, file ID, path, qualified name, and source range against the selected hit. It then checks the loaded file's commit and path as well.

If those checks disagree, it asks the user to refresh rather than opening an unrelated definition under a reused ID. The original API also scopes both detail endpoints to the selected repository.

## Jumping without rendering the entire file

Source remains paged at 200 lines. A definition starting at line 222 belongs to zero-based page 1:

```text
floor((start_line - 1) / 200)
```

Selecting a symbol switches to the Source tab and selects that page. The component scrolls the source pane to the definition and highlights every visible line between its start and end, inclusive. Larger definitions stay highlighted when the user visits additional pages. A banner names the selection and offers a clear control.

The repository explorer scrolls into view once a selection loads. Scrolling inside the code pane does not scroll or clip the surrounding controls. The GitHub link includes the selected line range at the indexed commit.

## Code map

- `backend/app/index.py`: literal matching, ranking, counting, and paging.
- `backend/app/main.py`: search parameter validation and response handling.
- `frontend/components/symbol-search.tsx`: term/filter/page state and debounced requests.
- `frontend/lib/api.ts`: search requests and stale-index navigation checks.
- `frontend/lib/source-range.ts`: page calculation and inclusive range checks.
- `frontend/components/source-viewer.tsx`: page selection, highlighting, and source scrolling.

No tables or columns change in this milestone.

## Verification

Backend tests cover ordering, page totals, scopes, signatures, paths, imports, type filters, literal wildcard characters, Unicode literals, syntax-error flags, unavailable parses, and parameter limits. Re-ingestion tests verify that obsolete results are invalidated.

Frontend tests cover encoded search parameters, navigation identity checks, commit changes between requests, page boundaries, and inclusive highlighting. Browser checks use the saved `itsdangerous` index to search and open `Signer.sign` at lines 222–225 on the second source page, and exercise filtering and pagination.

## Next milestone

Build explicit containment and local import relationships from the parsed source. Those graph records will support incoming/outgoing dependency inspection and later visualization.
