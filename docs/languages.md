# Source language support (v0.22)

CodeAtlas indexes Python, JavaScript, and TypeScript in the same repository. Re-index an existing repository to discover its additional files. The workspace includes a language filter and shows each file's actual language in the source viewer. `/capabilities` lists supported languages; repository overviews include file counts grouped by language.

| Language | Files | Definitions |
| --- | --- | --- |
| Python | `.py` | Functions, classes, methods, imports |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | Functions, bound arrow/function expressions, classes, methods, imports |
| TypeScript | `.ts`, `.tsx`, `.mts`, `.cts` | JavaScript definitions plus interfaces and type aliases |

JSX and TSX are parsed with their appropriate grammars. Anonymous default-exported functions/classes use the name `default`. Anonymous inline callbacks are not separate symbols. Arbitrary variables, computed property names, and ambient overload signatures are not a complete type index. Source files remain viewable even when syntax recovery reports errors. The recovery flag reflects the pinned grammar, not a compiler or type checker: valid syntax outside that grammar can also be flagged (for example, bare ampersands in JSX text with the current TSX grammar).

## Dependencies and calls

Python retains its existing module and relative-import resolution. Script files resolve relative ES imports, `export ... from` re-exports, literal CommonJS `require()` and literal dynamic imports. The graph records syntactic references, including type-only imports; it is not a runtime dependency graph.

Resolution uses exact files, extensionless source paths, and directory `index` files. Explicit `.js` imports can fall back to `.ts`/`.tsx` sources when no exact JavaScript file exists; `.mjs`/`.cjs` can fall back to `.mts`/`.cts`. Multiple matches in a resolution tier are ambiguous rather than guessed. Case-sensitive source paths stay distinct. Script imports never resolve into Python files, and Python module lookup ignores script files.

Bare npm packages, `tsconfig` aliases, bundler aliases, package exports, computed imports, and transitive re-export bindings are not resolved. The index never runs Node, installs a repository's dependencies, or evaluates its configuration.

JavaScript/TypeScript call targets currently cover same-file lexical candidates and direct `this.method()` candidates inside indexed class methods. Imported calls, arbitrary receiver types, object prototypes, and runtime rebinding remain unresolved. Python's existing imported-function and `self`/`cls` candidates are preserved. All suggested call targets are approximate, not proof of runtime dispatch.

Symbol search, semantic retrieval, cited questions, impact, architecture, and PR mapping operate on the mixed-language index. Semantic ranking still uses the same general local embedding model; adding a grammar does not imply a language-specific relevance benchmark. Architecture branch counts use each file's grammar, including script conditionals, loops, catch blocks, switch cases, and logical operators.

## Storage and limits

No database schema migration is needed: files already have a language field, and symbol kinds are stored as text. Per-file index format `3` invalidates older syntax caches once. Subsequent runs reuse unchanged file indexes as before; global dependencies and candidate links are rebuilt. Existing source remains intact until a successful indexing transaction replaces it.

The limits apply across **all supported languages combined**: 2,000 source files, 25 MB total source, 1 MB per file, 100,000 symbols, 100,000 calls, and 300,000 relationships. The existing clone/storage/time limits, UTF-8-only reads, and symlink exclusions remain. JavaScript dependency/build directories (`node_modules`, `.next`, `.nuxt`, `.output`, `.turbo`, `out`, `dist`, `build`) are excluded.

Grammar versions are pinned alongside the existing Tree-sitter runtime. Parsing never executes repository source. HTML, CSS, JSON, Lua/Luau, and other languages are not structurally indexed in this release.
