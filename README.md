# CodeAtlas

A code intelligence platform that will turn a public GitHub repository into an explorable index of files, symbols, and dependencies.

The project starts with Python and structural analysis. Search and AI features will build on a real index later.

## Current milestone: repository metadata storage

The API can register a GitHub repository URL, save its metadata in SQLite, and list or retrieve saved records. Records survive application restarts. Cloning, file discovery, parsing, and the frontend are upcoming milestones.

### Run locally

Requires Python 3.11 or newer.

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

### Run the tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## How this step works

1. Startup creates the database tables from the SQLAlchemy model in `backend/app/models.py`.
2. FastAPI validates the request using the Pydantic schema in `backend/app/schemas.py`.
3. Each request gets its own database session. Registration commits its new repository record; a duplicate rolls the transaction back.
4. The response schema exposes the saved metadata as JSON, including its ID and UTC creation time.
5. Tests use separate temporary databases, including a test that closes and recreates the application to check persistence.

The endpoint checks that the API process responds. It does not check a database or other services yet.

See [the metadata walkthrough](docs/metadata-storage.md) for an explanation of tables, sessions, transactions, and the application factory.

See [the roadmap](docs/roadmap.md) for the next steps.
