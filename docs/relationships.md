# Phase 8: structural relationships

Parsing now saves directed edges alongside the symbols in the same transaction:

- `contains`: a file or definition directly contains a symbol. Exact parser object identities preserve parentage when names repeat; imports inside functions belong to that function.
- `imports`: an import statement points to a saved Python module file when one candidate resolves uniquely. Unresolved and ambiguous statements remain visible without a target.

The resolver reads Python import syntax using `ast.parse` on statements extracted by Tree-sitter. It never imports or executes repository code. Aliases retain the original module dependency. Each name in an import statement gets its own edge; wildcard imports link only to the module.

Supported module layouts are repository-root Python modules/packages and the conventional `src/` layout, including namespace packages. Relative imports use the importing file's package. `from package import name` first looks for the submodule, then the package file. Duplicate candidates are ambiguous; no target is guessed. Future imports have no local dependency.

These are static file dependency candidates, not verified runtime bindings or symbol reference resolution. External packages, custom source roots, dynamic imports, re-exports, and Python path modifications are not resolved. Recovered syntax from invalid files may be incomplete. Import resolution does not determine call targets.

## API

`GET /repositories/{repository_id}/files/{file_id}/relationships`

Query parameters: `kind=contains|imports` (optional), `direction=outgoing|incoming`, `limit` (1–100, default 30), and `offset`. Incoming results are imports targeting the selected file. Pages include the snapshot commit, readiness, total, source/target IDs, file paths, source lines, and resolution status. Reads use the existing consistent index transaction.

The website's file relationships panel switches between containment, imports, and importers, pages results, and opens linked files. Late responses are ignored after navigation and mismatched commit responses ask for a refresh.

New tables require no changes to existing tables. Previously parsed repositories show a re-index prompt until parsed again. Re-ingestion clears the graph; re-parsing replaces it atomically with the symbols. A failed extraction or write rolls back the entire replacement. Graph construction is limited to 300,000 edges.

Run backend tests with `.\.venv\Scripts\python.exe -m pytest backend/tests -q`, and frontend checks with `npm test` and `npm run build` from `frontend/`.
