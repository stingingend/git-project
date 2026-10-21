# Milestone 3: ingestion and file discovery

The last milestone remembered a GitHub URL. This one collects the actual Python source behind it, without parsing or executing the code.

## Follow one ingestion

```text
POST /repositories/{id}/ingest
    → look up the registered URL
    → acquire the ingestion lock
    → shallow-clone into a temporary directory
    → discover eligible tracked Python files
    → read source and compute hashes and line counts
    → remove the temporary clone
    → replace the saved snapshot in one transaction
    → return metadata
```

Registration and ingestion remain separate endpoints. That keeps the earlier registration API usable and gives the next stages a repository ID to work with.

## Why no checkout?

A Git repository stores file content as objects called blobs. The working tree is a separate copy of those files that people normally edit. The ingestion service only needs the blobs.

`git clone --no-checkout` avoids creating the working tree. `git ls-tree` lists tracked paths, object types, modes, blob hashes, and sizes at `HEAD`. `git cat-file blob <hash>` reads a chosen blob's bytes. The service can exclude symlinks and oversized files before reading their contents.

The clone is shallow and limited to the default branch. Its commit hash identifies the exact source collected, even if the repository changes later.

## What gets saved?

`source_files` stores the repository ID, path, language, source text, SHA-256 hash of the original bytes, and line count. `repository_snapshots` stores one current snapshot per repository: commit, branch, timestamp, counts, and skipped files.

These are new tables, so registered repositories from milestone 2 remain usable without changing their table. Full schema migrations are still a later task.

The source is saved now so the next milestone can parse a stable snapshot without cloning it again. The file-list endpoint returns metadata only.

## Limits and exclusions

The service enforces clone time and disk limits, limits tracked entries and eligible Python source, and skips large individual files. It excludes generated/vendor/cache folders, symlinks, non-Python files, and non-UTF-8 source. An empty eligible file set is valid.

Git uses an isolated environment with no saved credential helpers and no HTTP redirects. A private or inaccessible repository fails instead of opening a sign-in prompt. Process-tree termination stops Git's transport children on timeout or disk-limit failure.

The clone directory exists only inside a context manager. Leaving that context removes it, including when discovery raises an error. These protections support local development; they do not replace resource-isolated workers for public hosting.

## Re-ingestion and failure

Discovery finishes before database changes begin. The service then deletes the previous file rows, inserts the replacement set, updates the snapshot, and marks the repository `ingested`. The endpoint commits these changes together.

If cloning or discovery fails, the previous snapshot is untouched. If a database write fails, the transaction rolls back. This prevents a half-replaced snapshot. A per-process lock rejects a second simultaneous ingestion with `409`; use one worker until background job coordination exists.

## What the tests establish

- A real Git fixture includes ordinary source, an empty file, a BOM, ignored vendor code, unsupported encoding, and a symlink entry.
- Discovery produces exactly the expected files, hashes, line counts, and exclusions.
- Source containing a top-level exception is read without executing it.
- Re-ingestion replaces records without duplication, and snapshots survive application restart.
- Failed first ingestion and failed re-ingestion preserve the correct stored state.
- Simulated clone timeout and disk limits stop the transport and remove temporary files.

## Next step

Tree-sitter will turn the saved Python source into syntax trees and extract functions, classes, methods, and imports. Ingestion will remain responsible for collecting source; parsing will be a separate stage.
