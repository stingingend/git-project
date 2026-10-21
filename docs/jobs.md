# Phase 12: background indexing jobs

The website's Index repository and Re-index actions now submit a background job. The API responds with `202 Accepted` after saving its job record; the browser polls its ID for progress. Reloading the page finds the most recent saved job and reconnects. Closing the tab does not cancel indexing. Recent indexing runs shows saved statuses, stages, timestamps, errors, and the ingested commit when available.

Progress reflects real stages, not estimated percentages:

1. Registration connects the repository metadata in the browser.
2. A queued job record is committed before the worker starts.
3. The worker ingests Python source while reporting `running / ingesting`.
4. Ingestion and its `parsing` stage update commit together.
5. Parsing and the `succeeded / complete` result commit together.

The UI checks status every second while running and backs off to two seconds after connection failures. It keeps monitoring after a temporary disconnect. Missing job IDs stop monitoring with an error. Finished jobs refresh the repository index. The current UI disables workspace mutations and file selection during an active job to avoid stale snapshot navigation.

## API

- `POST /repositories/{id}/jobs`: start indexing; return the saved job with 202. A duplicate submission for the same active repository returns the existing job ID. Another repository's active operation returns 409.
- `GET /jobs/{job_id}`: fetch a job or return 404.
- `GET /jobs?limit=10`: recent jobs, newest first; limit 1–50.

Job records include UUID ID, repository ID, status (`queued`, `running`, `succeeded`, `failed`, or `interrupted`), stage (`queued`, `ingesting`, `parsing`, or `complete`), creation/start/finish timestamps, error, and commit SHA. Creation/start/finish timestamps are UTC. Expected ingestion/parser errors are retained; unexpected failures expose a generic error while details stay in API logs.

The existing synchronous `/ingest` and `/parse` endpoints remain available for manual/API clients. They share the same lock as background jobs and reject conflicting operations. Only one job runs at a time; additional repositories are rejected rather than accumulated in an unbounded queue.

## Transactions, shutdown, and recovery

Each job has a dedicated worker thread and uses its own database sessions. HTTP requests remain available during ingestion/parsing. The worker uses the same safe Git ingestion, resource limits, parser, and transactional replacement as earlier phases. Source is never executed.

The ingestion and parsing stages have separate transactions. Failed ingestion preserves the previous snapshot. Successful ingestion replaces source and clears the old parsed index; if parsing then fails, the newly ingested snapshot remains available but unparsed. This phase does not stage and publish an entire job atomically.

A graceful API shutdown waits for the current operation to finish. Compose allows 120 seconds before forcing a stop. On startup, any remaining queued/running job is marked interrupted with a finish timestamp and a retry message. Recovery does not silently resume partial work or initiate another network clone; start indexing again explicitly. If a database outage prevents recording a failure, a job may retain its last saved status until startup recovery.

Run **one API process, one Uvicorn worker, and one API instance per database**. The executor and lock are process-local. Job records are durable; the execution queue is not a distributed/retry queue. Do not start another API against the same database while indexing. Distributed coordination, cancellation, automatic retries, and retention policies are future work.

New `index_jobs` storage is created at startup without changing existing tables. SQLite remains the local default; PostgreSQL and Docker use the same worker implementation. No credentials or extra service are required for this phase.

Tests cover a blocked worker with responsive HTTP endpoints, stage transitions, duplicate requests, conflicts with synchronous indexing, expected/unexpected failures, retries, startup recovery, worker startup failure, validation, PostgreSQL sessions, and browser request sequencing. Browser verification submits a real public repository and reloads to recover its saved result.
