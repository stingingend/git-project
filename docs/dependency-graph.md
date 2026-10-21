# Phase 10: dependency visualization

Select a Python file in the repository explorer and scroll to **Explore the connections**. The selected file sits in the center; incoming importers appear on the left and dependencies on the right. Click a connected file to load its source and make it the new center. Buttons support keyboard navigation, and a screen-reader list describes the directed links.

Arrows run from the importer to the imported module file. Repeated import links between a pair of files are combined and labeled with a count. Counts represent saved import bindings, not unique import statements: `from module import a, b` contributes two links. A file connected in both directions appears on the dependency side, with two separate arrows and an explicit label.

The view shows only the selected file's immediate local dependencies and importers, not transitive relationships or calls. It includes up to 12 unique neighboring files, ordered by path. The summary shows the full neighbor count and explains truncation. File relationships below the graph remains paginated for browsing all individual imports. The diagram scrolls for narrow screens and large neighborhoods.

Unresolved or ambiguous imports are counted but do not become invented target nodes. Self-imports are counted separately. Recovered syntax and static resolution limits from [phase 8](relationships.md) still apply. An empty view means no resolved local links were found, not that the file has no runtime dependencies.

## API

`GET /repositories/{repository_id}/files/{file_id}/graph`

Returns `file_id`, `ready`, `commit_sha`, `total_neighbors`, `unresolved_imports`, `self_imports`, `nodes` (`id`, `path`), and directed `edges` (`source`, `target`, `count`). The selected file is the first node. At most 13 nodes and 24 directed edges are returned. Unknown or foreign files return 404.

The endpoint reads the existing relationship tables in one consistent index transaction, so it requires no schema changes or re-indexing for an existing phase 8 index. Unparsed or invalidated indexes return `ready: false`. The UI ignores late responses after navigation and rejects mismatched file identities or commit hashes. Use Reload graph to retry a failed request; refresh the repository if its index has changed.

Backend checks cover direction, repeated bindings, self-imports, unresolved targets, empty and unparsed indexes, repository scope, invalidation, stable truncation, and PostgreSQL aggregation. Frontend checks cover layout, reverse links, row bounds, and API request scoping. The graph uses native SVG and buttons, with no graph-library dependency.
