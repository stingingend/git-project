# Phase 11: approximate call analysis

Select a Python file and open **Calls** beside Source and Symbols. Each row shows the callable expression, its line and column, the enclosing definition (or module), and any suggested target. Filter the list to possible targets, ambiguous calls, or unresolved calls. Selecting a possible target opens its source and highlights the definition; the line link opens the call site on GitHub at the saved commit.

## What is extracted

Tree-sitter extracts `call` nodes without importing or executing source. Nested calls are separate records. Calls are classified as direct names (`helper()`), attributes (`object.helper()`), or dynamic expressions (`factories[0]()`), with one-based line ranges and one-based UTF-8 byte columns. Callable labels are capped at 300 characters; the source link retains the complete call range.

The enclosing definition is a syntactic container, not a runtime caller. For example, a call in a function's default parameter is syntactically inside that definition even though Python evaluates it when defining the function. Calls inside lambdas or comprehensions retain the nearest extracted enclosing definition; this phase does not create separate lambda scopes.

## Suggestions and limits

Direct-name calls search definitions in the nearest enclosing scope, then outer lexical scopes, then the module. Function bodies skip enclosing class namespaces. Exact parent identities distinguish repeated/nested definitions. A unique matching function or class is a **possible target**; duplicate names in the selected scope are ambiguous, with no target chosen. Recursive calls and calls to constructors can have candidates.

This is a name-based approximation. Assignments, parameter shadowing, imports with the same name, aliases, conditional definitions, evaluation order, decorators, monkey-patching, and other runtime behavior can change a target. This phase does not perform binding/data-flow analysis. Attribute calls (including `self.method()`), imported definitions, cross-file calls, and dynamic callable expressions remain unresolved. Built-ins have no same-file definition unless the file defines that name. A candidate is never labeled a verified/resolved call.

Recovered syntax from invalid files can be incomplete. The source viewer retains its syntax-error warning. Unresolved means no same-file target was suggested, not that Python cannot execute the call.

## Storage and API

`GET /repositories/{repository_id}/files/{file_id}/calls`

Query parameters: optional `resolution=candidate|ambiguous|unresolved`, `limit` (1–100, default 30), and nonnegative `offset`. Results include readiness, snapshot commit, parse-error status, unfiltered summary counts, filtered total, and a stable page ordered by line, byte column, and ID. Each item includes its enclosing and target symbol records when available. Files outside the requested repository return 404.

Call sites and a repository-level call snapshot use new tables; existing columns are unchanged. Startup creates the tables. Previously parsed repositories show a re-index prompt until parsed again. Call extraction has a separate limit of 100,000 calls per repository. Parsing replaces symbols, imports, and calls in one transaction; re-ingestion clears them together. Failures preserve the previous index. Call-site foreign keys are deleted before replacing symbols.

The UI checks the file ID and commit hash and ignores late responses after navigation. Target navigation uses the existing symbol-identity and source-commit validation.

Tests cover nested expressions, recovered syntax, scope selection, recursion, class namespace rules, repeated names, filtering, paging, repository scope, limits, rollback, invalidation, PostgreSQL foreign keys, and request parameters. Browser verification checks filtering and jumping from a call to highlighted source.
