# CodeAtlas

CodeAtlas is a source browser for public GitHub repositories. Give it a repository URL to browse files, find definitions, and see which parts of the code depend on each other.

It supports Python, JavaScript, TypeScript, C, and C++. Indexing and search run on your server. You don't need an API key unless you choose to use an external model server for generated explanations.

## What it does

- Search definitions by name, signature, or file path, then jump to the source.
- Browse imports and includes in a dependency graph, and inspect possible function calls.
- Search with a description of what the code does. Questions return matching source excerpts and links to GitHub.
- Check dependent files, import cycles, and changed definitions in public pull requests.
- Re-index after a change. Unchanged files reuse their existing index, and indexing keeps running if you close the tab.

Call matches and change-impact reports are approximate. They can help you find code to check, but they don't prove what will run or break. See [language support](docs/languages.md) for details.

## Run with Docker

With Docker Desktop running, open PowerShell in the repository root:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose --env-file .env.docker up --build --wait
```

Open [localhost:13000](http://127.0.0.1:13000), then choose **Open workspace**. Paste a public GitHub URL and click **Index repository**. `https://github.com/pallets/itsdangerous` is a small project to try first.

This setup includes PostgreSQL. See [Docker setup](docs/deployment.md) for configuration and storage details.

## Run without Docker

You'll need Python 3.11 or newer, Node.js 24 with npm, and Git on the API server's PATH. The commands below use PowerShell.

From the repository root, start the API:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[test]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001
```

In a second terminal, start the website:

```powershell
cd frontend
npm ci
npm run dev
```

Open [the workspace](http://127.0.0.1:3000/workspace). The API docs are at [localhost:8001/docs](http://127.0.0.1:8001/docs). Press **Ctrl+C** in each terminal to stop the servers.

The API uses a local SQLite file, `codeatlas-metadata.db`, and applies migrations on startup. Set `DATABASE_URL` to use another database. If the API runs at a different address, copy `frontend/.env.example` to `frontend/.env.local`, set `API_URL`, and restart the frontend. For production, set it before building.

## How it works

The backend downloads a shallow Git snapshot and reads supported source files without executing them. Tree-sitter extracts definitions, imports, and call sites. The results are stored in SQLite or PostgreSQL and served through FastAPI to the Next.js frontend.

Source links point to the indexed Git commit. Re-index to see newer changes. The optional semantic index uses Model2Vec on the server; its model downloads on the first build. Generated explanations need a separately configured model server.

Run one API process per database. Indexing uses local background workers; multiple API instances aren't supported. The [Render guide](docs/hosting.md) covers hosting a personal workspace behind a password. Private repositories and posting PR comments aren't supported.

## Documentation

| Topic | Guides |
| --- | --- |
| Using the explorer | [Frontend](docs/frontend.md), [symbol search](docs/symbol-search.md), [dependency graph](docs/dependency-graph.md) |
| Supported code | [Languages](docs/languages.md), [calls](docs/calls.md), [cross-file calls](docs/cross-file-calls.md) |
| Search and questions | [Semantic search](docs/semantic-search.md), [questions](docs/questions.md) |
| Reviewing changes | [Impact and architecture](docs/impact-and-architecture.md), [pull requests](docs/pull-requests.md) |
| Indexing and storage | [Ingestion](docs/ingestion.md), [parsing](docs/parsing.md), [metadata](docs/metadata-storage.md), [relationships](docs/relationships.md), [index inspection](docs/index-inspection.md), [incremental indexing](docs/incremental.md), [jobs](docs/jobs.md) |
| API examples | [Registration, indexing, and queries](docs/api-guide.md) |
| Running a server | [Docker](docs/deployment.md), [Render](docs/hosting.md), [migrations](docs/migrations.md), [release checks](docs/release.md) |
| Project status | [Roadmap](docs/roadmap.md), [benchmarks](docs/benchmarking.md) |

## Development checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

From `frontend/`:

```powershell
npm test
npm run typecheck
npm run build
```

To measure indexing with a generated fixture and an isolated database:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_index.py --files 100 --changed 4 --repeat 3 --semantic --output docs/benchmark-latest.json
```

See [benchmarking](docs/benchmarking.md) for the recorded results and what the timings include.
