# Milestone 2: repository metadata

This step gives the application memory. The API skeleton could answer requests, but it could not remember anything after it stopped. SQLite now stores repository records in a file.

## What is a repository record?

The `Repository` model describes one row in the `repositories` table:

| Column | Purpose |
| --- | --- |
| `id` | A generated primary key that identifies the record |
| `github_url` | The canonical URL, protected by a unique constraint |
| `owner` | The GitHub user or organization from the URL |
| `name` | The repository name from the URL |
| `status` | `registered`, because ingestion has not happened yet |
| `created_at` | When the record was registered, using UTC |

These values come from the submitted URL and the application itself. They are not fetched from GitHub. Branches, commit hashes, and indexing times will only make sense once ingestion exists.

## Follow a request

For `POST /repositories` with `{"github_url":"https://github.com/Pallets/Flask.git"}`:

1. `RepositoryCreate` checks the URL format and normalizes it to `https://github.com/pallets/flask`.
2. The route derives `pallets` and `flask` from the normalized URL.
3. It constructs a `Repository` object and adds it to the request's session.
4. `session.commit()` writes the row and finishes the transaction.
5. `RepositoryRead` turns the saved object into the JSON response.

A session is the request's interface to the database. A transaction groups database changes into a unit that can either succeed or be rolled back. Closing the session releases its resources; it does not erase committed rows.

## Why use a database constraint for duplicates?

Checking whether a URL exists before inserting it would leave a race: two requests could both check before either inserts. The unique constraint enforces the rule inside the database. If an insert violates it, the route rolls back the transaction and returns `409 Conflict`.

## Why have `create_app()`?

The application factory accepts a database URL. Normal startup uses `DATABASE_URL` or the local SQLite default. Tests pass a temporary database URL instead, keeping test records separate from development data.

FastAPI's lifespan creates missing tables at startup and disposes of the engine when the application shuts down. Creating tables is sufficient for this milestone; changing an existing schema later will require migrations.

## What proves persistence?

The restart test creates a repository through one application instance, shuts it down, then creates another instance pointing to the same database file. The second instance must return the original record, including its ID and creation time.

## Next step

Ingestion will contact GitHub, clone a repository temporarily, and discover supported source files. That step needs timeouts, size limits, and cleanup before parsing is added.
