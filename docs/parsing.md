# Milestone 4: Python symbol extraction

Ingestion collected source text. Parsing turns that text into structured definitions without importing or executing it.

## Follow the data

```text
Saved source at a Git commit
    → Tree-sitter Python syntax tree
    → iterative tree traversal with enclosing scope
    → functions, classes, methods, and import statements
    → stored symbols, file flags, and parse summary
```

`parser.py` only handles source-to-symbol extraction. `parsing.py` handles loading source and saving results. The API owns the transaction and processing lock. Keeping these responsibilities separate makes parser fixtures independent of Git, HTTP, and the database.

## What does a syntax tree provide?

For this source:

```python
class PaymentService:
    async def charge(self, customer):
        return customer
```

Tree-sitter produces a `class_definition` containing a `function_definition`. The extractor reads the name and body fields from those nodes. It identifies `charge` as a method because its nearest enclosing definition is a class.

If a function is declared inside that method, its nearest enclosing definition is a function, so it becomes a nested function rather than a method. Decorators and `async` syntax do not change that scope rule.

## What is stored for each symbol?

| Field | Example |
| --- | --- |
| `file_id` | The saved source file's ID |
| `name` | `charge` |
| `qualified_name` | `src/payments.py::PaymentService.charge` |
| `parent_qualified_name` | `src/payments.py::PaymentService` |
| `symbol_type` | `method` |
| `start_line`, `end_line` | `2`, `3` |
| `signature` | `async def charge(self, customer)` |

The path prefix identifies the file without guessing Python import roots. Enclosing names distinguish definitions in different classes or functions. Overloads can still share a qualified name, so it is not a unique database key; each record also has its own ID and source range.

Signatures come from the source bytes between the definition's start and its body. This preserves multiline parameters and annotations. Definition ranges exclude decorator lines and use 1-based inclusive line numbers. Import signatures preserve the whole statement.

## Why use an iterative traversal?

The extractor keeps a stack of nodes and their nearest enclosing definition. Visiting a definition changes the context carried to its children. This follows the syntax hierarchy without consuming Python's call stack for each nested expression.

Traversal counts symbols and rejects a repository above 100,000 extracted records. This is an application limit, not a hard quota on the native parser's CPU or memory.

## What happens with broken Python?

Tree-sitter can recover a partial tree from malformed source. The extractor retains definitions it can identify and marks the file with `has_parse_errors`. The summary reports how many files have that flag. `parsed` means the extraction stage finished; it does not prove the source is syntactically or semantically valid.

No call resolution or dependency edges are built yet. Imported names remain statement records, and parent scope is descriptive metadata. Graph relationships come in a later milestone.

## Keeping snapshots consistent

Parsing reads the stored source, not the current remote repository. The parse summary saves the ingestion commit hash alongside its counts and timestamp.

Extraction completes before stored results are replaced. The delete-and-insert operations happen in one transaction, so a limit or database failure preserves earlier results. Re-ingestion clears symbols and parse summaries in the same transaction as source replacement, preventing stale file IDs or symbols from being shown against a new snapshot.

Parsing and ingestion share a per-process lock. This works for the single-worker local app; coordinating multiple workers is a later milestone.

## Check it yourself

Register and ingest a small Python repository, then call `POST /repositories/{id}/parse`. Inspect the summary and request `/symbols?kind=method`. Pick a symbol, find its file in `/files`, and compare the reported line range to the indexed commit on GitHub.

Parser tests cover async and nested definitions, decorators, Unicode, multiline signatures, imports, repeated overloads, syntax errors, deep trees, and symbol limits. API tests cover persistence, filtering, paging, rollback, and re-ingestion invalidation.

## Next milestone

Add a repository index overview and file/source inspection endpoints, combining the ingestion and parse data into something a frontend can consume directly. Search and visualization remain separate steps.
