# Phase 14: schema migrations

Startup applies packaged Alembic revisions in order. `001_baseline` freezes the phase-13 schema and adopts compatible existing tables without rewriting records. It rejects tables missing required columns. `002_job_history` adds a composite job-history index. Future schema changes belong in new revisions; never edit the frozen baseline or use current application metadata inside old revisions.

To upgrade separately from API startup, set `DATABASE_URL`, then run from the repository root:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.migrations
```

Back up the database before an upgrade. SQLite upgrades use an explicit transaction; PostgreSQL upgrades use a transaction and advisory lock. Unknown revisions and failed upgrades stop startup. Automatic downgrade is not provided: restore a backup when reverting application releases. Continue to run only one indexing API instance per database.

The implementation follows [Alembic's shared-connection recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands). Tests check fresh creation, repeat upgrades, preserving a legacy repository, and refusing incompatible tables. PostgreSQL and restart-with-volume checks also run in CI.
