# CodeAtlas

A code intelligence platform that will turn a public GitHub repository into an explorable index of files, symbols, and dependencies.

The project starts with Python and structural analysis. Search and AI features will build on a real index later.

## Current milestone: API skeleton

The first step is a small FastAPI application with a health endpoint and a test. Database storage, repository ingestion, parsing, and a frontend are upcoming milestones.

### Run locally

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[test]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1
```

Open [the health endpoint](http://127.0.0.1:8000/health) or [the API documentation](http://127.0.0.1:8000/docs).

Expected response from `GET /health`:

```json
{"status": "ok"}
```

### Run the test

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## How this step works

1. Uvicorn runs the ASGI application in `backend/app/main.py`.
2. FastAPI routes a `GET /health` request to the `health` function.
3. FastAPI serializes the returned dictionary as JSON.
4. The test sends a request in-process and checks the status code and response body.

The endpoint checks that the API process responds. It does not check a database or other services yet.

See [the roadmap](docs/roadmap.md) for the next steps.
