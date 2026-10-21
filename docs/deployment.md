# Phase 9: PostgreSQL, Docker, and CI

## Existing local setup

SQLite remains the default. The two-terminal Python/Next.js setup in the README still works. `/health` checks process liveness; `/ready` verifies a database query and returns 503 if the database is unavailable.

## Run the complete stack

Install Docker Desktop with Linux containers and Compose v2. From the repository root in PowerShell:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose --env-file .env.docker up --build --wait
```

Open **http://127.0.0.1:13000**. The container API docs are at **http://127.0.0.1:18001/docs**. These ports are separate from the existing local servers on 3000 and 8001. Change `WEB_PORT` or `API_PORT` in `.env.docker` if needed. These settings affect only host ports; containers communicate over their internal service names.

The database has a named volume and no host port. API/web ports bind to localhost. The API and web containers run as non-root users. API startup waits for PostgreSQL health, and web startup waits for API readiness. The web health check traverses the Next.js proxy to the API/database. Compose's [health-based dependency ordering](https://docs.docker.com/compose/how-tos/startup-order/) handles initial startup.

The API image includes Git for ingestion and the PostgreSQL driver. The web image uses [Next.js standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output); its `API_URL=http://api:8001` rewrite is fixed at build time. A changed API destination requires rebuilding the web image. Standard local builds still use `next start`.

Useful commands:

```powershell
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 100
docker compose --env-file .env.docker down
```

`down` preserves the database volume. Start again with `up --wait` to reuse the data. PostgreSQL's initialization password is applied only when creating a fresh volume; editing the environment file does not rotate an existing database password. The example password is for this local development stack. Use URL-safe letters/digits because the password is included in a connection URL.

Docker starts a separate PostgreSQL database. It does not copy or replace existing SQLite data. Register and index repositories in the Docker interface to populate that database. Schema startup creates missing tables; automatic schema migrations and SQLite data transfer are not implemented yet.

Run only **one API worker and one API instance** against a database. Background indexing uses a local worker thread and shares the process-local ingestion/parse lock. Compose allows 120 seconds for graceful API shutdown. See [background jobs](jobs.md) for progress, interrupted-job recovery, and limitations. Distributed locking is later work. This setup is for local use; authentication and public hosting are not part of this phase.

## PostgreSQL without Docker

Provision a PostgreSQL database, then install the optional driver and set its connection URL before starting the API:

```powershell
.\.venv\Scripts\python.exe -m pip install -e './backend[postgres]'
$env:DATABASE_URL = 'postgresql+psycopg://user:password@localhost:5432/codeatlas'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Plain `postgresql://` and `postgres://` URLs select the Psycopg 3 driver too. Connection values containing reserved URL characters must be percent-encoded. For multi-query index reads, PostgreSQL uses `REPEATABLE READ` to avoid mixing source/symbol generations if a concurrent indexing transaction commits. See [SQLAlchemy's PostgreSQL driver and isolation documentation](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).

## Automated checks

GitHub Actions runs on pushes to main, pull requests, and manual dispatch:

- Backend suite on Ubuntu and Windows, using Python 3.12 and SQLite.
- Opt-in PostgreSQL 17 integration tests for index/search/graph operations, replacement, rollback, persistence, and snapshot consistency.
- Frontend unit tests and a production build on Node 24.
- Actual container builds, health checks, web/API proxy smoke checks, and persistence after containers are recreated with the same volume.

PostgreSQL integration tests use a fresh random schema per test and remove only that schema. Run them against a disposable test database with permission to create schemas:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql+psycopg://user:password@localhost:5432/codeatlas_test'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_postgres.py -q
```

Without this environment variable the PostgreSQL tests skip; the SQLite suite remains usable. To run the Compose smoke check after starting the stack, use `.\.venv\Scripts\python.exe scripts/smoke_stack.py`. It registers `example/compose-smoke` as metadata without cloning source; `--expect-existing` checks persistence without registering it again.
