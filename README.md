# CodeAtlas

A code intelligence platform that will turn a public GitHub repository into an explorable index of files, symbols, and dependencies.

The project starts with Python and structural analysis. Search and AI features will build on a real index later.

## Current milestone: GitHub ingestion and file discovery

The API can register a GitHub repository, clone it temporarily, discover tracked Python files, and store a source snapshot in SQLite. The snapshot includes file hashes, line counts, the default branch, and commit hash. Parsing and the frontend are upcoming milestones.

### Run locally

Requires Python 3.11 or newer and Git on the API server's PATH.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[test]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1
```

Open [the health endpoint](http://127.0.0.1:8000/health) or [the API documentation](http://127.0.0.1:8000/docs).

The API creates `codeatlas-metadata.db` in the directory where you start it. This file is ignored by Git. You can set `DATABASE_URL` before startup to choose another SQLite database, for example:

```powershell
$env:DATABASE_URL = 'sqlite:///./my-codeatlas.db'
```

PostgreSQL setup and schema migrations will come in later milestones. For now, startup creates missing tables; it does not migrate existing tables when their columns change.

This milestone adds `repository_snapshots` and `source_files` tables without changing the existing `repositories` table. Restart the API after updating; startup creates the new tables alongside existing registered repositories.

Expected response from `GET /health`:

```json
{"status": "ok"}
```

### Register a repository

With the API running, open another PowerShell terminal:

```powershell
$body = @{ github_url = 'https://github.com/pallets/flask' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/repositories' -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/repositories'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/repositories/1'
```

The last command uses the ID returned by the first command; `1` is an example for a new database.

| Endpoint | Result |
| --- | --- |
| `GET /health` | Process liveness |
| `POST /repositories` | Register URL metadata; return `201` |
| `GET /repositories` | List registered repositories by ID |
| `GET /repositories/{id}` | Retrieve one record; return `404` if missing |

Registration accepts an HTTPS `github.com/owner/repo` URL. Trailing slashes and `.git` suffixes are normalized, and owner/repository casing is lowered. The unique URL constraint prevents duplicate records, returning `409`. Invalid URLs or payloads return `422`.

Registration validates the URL's format only. It does not contact GitHub, verify that a repository exists or is public, clone source, or index code. Its status is `registered` to make that distinction explicit.

### Ingest a registered repository

Using the ID returned by registration:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/repositories/1/ingest'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/repositories/1/snapshot'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/repositories/1/files'
```

For a smaller first example, register `https://github.com/pallets/itsdangerous`.

| Endpoint | Result |
| --- | --- |
| `POST /repositories/{id}/ingest` | Clone, discover, and save a source snapshot synchronously |
| `GET /repositories/{id}/snapshot` | Commit, branch, ingestion time, file count, skipped files, and total lines |
| `GET /repositories/{id}/files` | File paths, language, SHA-256 hashes, and line counts |

Successful ingestion changes the repository status to `ingested`. This means source has been collected; no symbols have been parsed yet. Re-ingestion replaces the snapshot atomically. A failure preserves the previous snapshot, or leaves a new repository `registered`. The temporary clone is removed before the database transaction commits. A repository with no eligible Python files succeeds with a file count of zero.

Ingestion runs in the request. Use one API process/worker: a per-process lock allows one ingestion at a time and returns `409` if busy. Clone/read/limit failures return `422`; missing records or snapshots return `404`. Background jobs and progress reporting come later.

### Ingestion limits

- HTTPS GitHub URLs only; Git redirects and credential helpers are disabled.
- Shallow, single-branch clone with no checkout, hooks from repository code, submodule traversal, or LFS downloads. Repository code and dependencies are never executed.
- Clone timeout: 90 seconds. Clone disk usage: 150 MB, checked while cloning and after it exits. Transport children are terminated on a limit failure. These application checks are not operating-system resource quotas.
- Up to 20,000 tracked entries, 2,000 eligible Python files, and 25 MB eligible Python source. Individual files over 1 MB are skipped.
- Tracked regular `.py` files only. Git symlinks and generated/vendor/virtual-environment/cache folders are skipped. Untracked local files are never scanned.
- UTF-8 and UTF-8 BOM source only; unsupported encodings are skipped. The skipped count refers to Python files excluded by these rules.
- Source text is saved for the next parsing milestone. The file-list API exposes metadata, not source text.

This is still a local development API. Public hosting needs authentication, rate limiting, and stronger worker isolation.

### Run the tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## How this step works

1. Register a canonical GitHub URL and get a repository ID.
2. The ingestion service clones it into a temporary directory without checking it out.
3. `git ls-tree` discovers tracked entries; `git cat-file` reads eligible blobs from that commit.
4. SQLAlchemy saves the source files, snapshot metadata, and `ingested` status in one transaction.
5. Tests use real local Git fixtures and isolated databases. Transport tests simulate clone failures and limits without depending on GitHub.

The `/health` endpoint checks that the API process responds. It does not check the database or GitHub.

See [the metadata walkthrough](docs/metadata-storage.md) for an explanation of tables, sessions, transactions, and the application factory.

See [the ingestion walkthrough](docs/ingestion.md) for Git objects, source discovery, and snapshot replacement.

See [the roadmap](docs/roadmap.md) for the next steps.
