# Local release and operational handoff

The remaining local feature roadmap is implemented. The release includes schema migrations, broader call candidates, local semantic retrieval, source-cited questions, impact, public PR reports/webhooks, architecture metrics, and benchmark tooling. Individual commits retain the milestones.

## Verify a release

1. Back up SQLite while the API is stopped, or use a PostgreSQL backup/snapshot. Preserve the database and model-cache volumes.
2. Install backend dependencies and frontend lockfile dependencies, then restart the API so migrations apply.
3. Check `/ready` and `/capabilities`; schema should be `005_pull_requests`.
4. Index a small public Python project. Re-index and confirm reuse counts, source navigation, calls, and graph interactions.
5. Build semantic vectors and run a query. Confirm citations point to the indexed SHA. Rebuild after changing snapshots.
6. Run impact/architecture. Analyze a public PR; a mismatched base must request targeted indexing, not fabricate mapping.
7. Run the automated checks and isolated benchmark in the README. CI additionally verifies actual containers and PostgreSQL/pgvector.

## Start, stop, and recover

Run one API process and one instance per database. Indexing and PR reports have separate bounded local workers; they are not distributed queues. Graceful shutdown waits for active work, with a 120-second Compose grace period. Startup marks unfinished saved work interrupted. Retry through the website. Logs retain unexpected error details; HTTP responses expose generic errors.

Compose's PostgreSQL volume and model-cache volume survive `docker compose down`. Do not remove volumes to apply code updates. Changing the initialization password in an environment file does not rotate an existing database password. Rebuild the web image after changing its API destination because rewrites are set at build time.

Semantic weights download on the first build. The pinned model and source vectors stay local. In Docker, the cache belongs to the unprivileged API user. For an optional local host model server from a Docker container, use `http://host.docker.internal:11434/v1`; otherwise use HTTPS for a hosted compatible server. Generation is requested explicitly per question. Model-server provisioning and credentials are not bundled with the application.

## External activation

The repository does not provision cloud accounts, incur hosting charges, expose localhost, register a GitHub App, configure private-repository OAuth, or publish PR comments. These need an account/hosting target and their own activation. The implemented GitHub integration reads public PRs and accepts authenticated webhook deliveries once a secret and reachable endpoint are configured.

For a future hosted instance, use a TLS endpoint and access controls, keep PostgreSQL private, restrict API access to the intended users/proxy, retain the one-instance constraint, provide persistent model storage, and configure backups and resource limits. A multi-instance deployment first needs shared coordination/queues and ownership of recovery.

Cloud rollout, private repositories, distributed workers, additional languages, and automated PR publishing are explicitly separate product extensions rather than silently enabled services.
