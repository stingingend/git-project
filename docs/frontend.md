# Milestone 6: a local web interface

This walkthrough describes the first frontend milestone. [Milestone 7](symbol-search.md) adds repository-wide search and in-page symbol navigation.

The project now has a Next.js frontend. A user can enter a GitHub URL and run the existing API workflow without finding endpoints or writing JSON in Swagger.

## Follow one interaction

```text
Repository form
    → POST /repositories
    → POST /repositories/{id}/ingest
    → POST /repositories/{id}/parse
    → GET overview + files
    → show saved results
```

Each indexing stage begins after the previous API request succeeds. The stage labels describe real requests, not timed progress animation. No background queue or completion percentage is implied.

If a repository URL is already registered, registration returns `409`. The frontend retrieves the repository list, finds that canonical URL, and uses its existing ID to re-ingest and parse. It does not pick an unrelated repository after an arbitrary conflict.

If ingestion fails, parsing never starts. If parsing fails, ingested source remains available according to the API's existing transaction behavior. The UI refreshes stored state after either success or failure, and shows the error.

## Browser and API addresses

The frontend runs on `http://127.0.0.1:3000`; the backend runs on `http://127.0.0.1:8001`. Browser requests go to `/api/...` on the frontend origin. A Next.js rewrite forwards those requests to FastAPI.

`API_URL` configures the server-side destination. It defaults to the local backend address and can be changed in `frontend/.env.local`. Restart Next.js after changing it; production builds must use the intended address at build time.

The proxy timeout allows the synchronous ingestion request to run longer than an ordinary quick GET. It does not turn the request into a background job. Keep the page open until indexing finishes.

## Code map

| File | Responsibility |
| --- | --- |
| `frontend/app/page.tsx` | Repository selection, form, stage state, statistics, file loading, errors |
| `frontend/components/source-viewer.tsx` | Source and symbol tabs, source paging, symbol paging, GitHub links |
| `frontend/lib/api.ts` | HTTP requests, readable errors, registration/ingestion/parsing sequence |
| `frontend/lib/types.ts` | TypeScript shapes matching the existing API responses |
| `frontend/next.config.ts` | Server-side proxy from `/api` to FastAPI |
| `frontend/app/globals.css` | Layout, theme, responsive rules, and focus states |

The indexing sequence lives outside the React component so it can be tested with fake HTTP responses. The backend remains responsible for canonical URL validation, ingestion limits, parsing, and database transactions.

## State and loading

React state tracks the repository list, selected repository, overview, files, selected file detail, indexing stage, and errors. Selecting another repository clears the previous file state before loading its overview.

When repository requests finish out of order, an effect cleanup prevents old results from replacing the current view. File requests use a monotonically increasing request ID so a slower earlier selection cannot overwrite a later one.

The UI disables indexing and repository-changing controls while an indexing request is in progress. It refreshes the index afterward because re-ingestion and re-parsing can replace file and symbol IDs.

## What is displayed?

All repository statistics come from stored overview responses. A dash means the corresponding stage has not completed; a completed stage with no results shows zero. Syntax-error and skipped-file counts remain visible.

The file filter matches the already-loaded paths. Source is displayed as React text with line numbers, so repository contents are not executed as HTML. Only 200 lines are rendered per source page. Symbol pages contain up to 100 records; each links to its source range at the indexed Git commit. The file list initially renders 100 matches, with a control to show more.

There is no global symbol search, in-page symbol highlighting, graph visualization, authentication, or public hosting in this milestone. Those remain separate steps on the roadmap.

## Verification

The frontend tests cover ordered requests, duplicate registration, validation errors, ingestion failure, parsing failure, disconnected/non-JSON responses, and symbol-page request parameters. TypeScript checking and a production build catch interface and bundling errors.

Manual browser validation exercises the real FastAPI server through the proxy: indexing a public repository, inspecting stored counts, opening a source file, changing source pages, switching to symbols, and handling an invalid URL. Backend tests remain separate and continue to validate parsing and storage behavior.

## Run it

Start FastAPI from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001
```

In another terminal, starting from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. See the README for first-time Python installation and frontend checks.

## Next milestone

Add repository-wide symbol search and selection that navigates to and highlights the matching source range. Structural relationships and their visualization follow later.
