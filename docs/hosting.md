# Hosting CodeAtlas on Render

The root `render.yaml` prepares a public Next.js product site, an owner-only workspace, a private FastAPI service, and persistent PostgreSQL. It does not create an account or activate billing by itself.

## Recommended first deployment

Use [Render Blueprints](https://render.com/docs/infrastructure-as-code) to deploy this repository. Keeping everything in the same region avoids cross-provider API routing and keeps the Python backend off the public internet. This is a single-owner deployment, not a multi-user SaaS account system.

The Blueprint uses a Starter web service (512 MB), Standard API service (2 GB, selected to leave room for Python parsing and embeddings), Basic-256mb PostgreSQL, 5 GB database storage, and 1 GB model-cache disk. Review the current [pricing](https://render.com/pricing) and the creation screen's total before accepting paid services. Costs include both running services, database compute/storage, and the disk; bandwidth and larger resource plans can add charges. Free services are unsuitable for this always-on backend and persistent model cache.

At the published prices checked on October 21, 2026, budget roughly **$40/month before tax and usage overages**: $7 web + $25 API + $6 database + approximately $2 storage. A Starter API would reduce this by $18/month, but its 512 MB limit needs a real indexing/embedding memory test before choosing it. The Blueprint intentionally keeps the 2 GB API until that is validated. A paid Pro workspace subscription is not required for this configuration.

1. Sign in to Render with the GitHub account that can access `stingingend/git-project`.
2. Choose **New → Blueprint**, connect that repository, and select `main`. The file is `render.yaml` at the repository root.
3. Enter `WORKSPACE_USERNAME` and a unique `WORKSPACE_PASSWORD` of at least 16 characters. The username cannot contain a colon. Keep these credentials in Render's secret environment settings, never in Git or `NEXT_PUBLIC_*` variables.
4. Review the paid resource summary, then create the Blueprint. Wait for the API/database and web builds to finish.
5. Open the web service's generated HTTPS URL. `/` is public; **Open workspace** leads to `/workspace` and the browser's sign-in prompt. Register a small public Python repository to verify indexing.
6. Build its semantic index and confirm the first model download can write to `/home/codeatlas/.cache/huggingface`. If the provider reports volume ownership errors, fix ownership for container UID 10001 through the service shell before retrying. Verify it again after a redeploy.

The deployment uses a fresh database. Existing local SQLite repositories are not uploaded automatically.

## Access boundary

The Next.js proxy authenticates `/workspace` and all `/api/*` paths before rewriting to FastAPI. Only `GET`/`HEAD /api/ready` is anonymous for health checks. Missing or partial hosted credentials return 503; wrong credentials return 401. Protected responses use `private, no-store` and `noindex`. Mutating browser requests with a different Origin or cross-site fetch metadata are rejected. The public home page, CSS, and icons remain accessible. Credentials are removed before forwarding requests to the backend.

The API must remain a Render **private service**, without an external URL or public proxy. Access control exists at the web boundary. Never expose the API port directly to the internet. Use HTTPS only for password authentication. Browser Basic authentication is intentionally a simple owner gate; browsers may retain credentials until the session ends. Use a separate browser profile on shared computers. User registration, per-user repository isolation, session logout, and rate-limited public sign-in require a separate account system before opening the workspace to general users.

Local development remains ungated when both workspace credentials and `WORKSPACE_AUTH_REQUIRED` are absent. To test hosted access locally, set all three environment variables before `npm start` and use a non-production test password.

## Service behavior and verification

- The frontend Docker build declares `API_INTERNAL_HOSTPORT`, supplied by the Blueprint's private service reference. Next.js constructs an internal HTTP rewrite at build time. Rebuild the frontend if that destination changes. Workspace credentials are runtime environment variables and never Docker build arguments.
- Keep exactly **one API instance and one Uvicorn worker**. The attached disk disables overlapping deploys and horizontal replicas. API deploys therefore have brief downtime. Do not add a separate pre-deploy migration process; startup already migrates and recovers interrupted jobs.
- Database access is private (`ipAllowList: []`). PostgreSQL startup migrations enable pgvector when the extension is available; the portable embedding store remains available otherwise. Check API logs for migration errors before using the workspace.
- The web health check traverses `/api/ready` to verify the backend and database. After deployment, check the home page, an unauthenticated `/api/repositories` request (401), authenticated indexing/search, and persistence after a redeploy.
- For a local production-build regression check, run `node scripts/smoke_hosted_web.mjs` from the repository root with the API running on port 8001. It launches temporary web servers and checks real proxy behavior, including missing credentials and forwarded HTTPS headers.
- Review PostgreSQL backup/restore settings and take a database backup before schema upgrades. Follow [migration operations](migrations.md). Model weights are a reconstructible cache, not the repository database.
- Optional external generation is off until configured on the API service. This Blueprint does not expose GitHub webhook intake: signed webhook forwarding needs a dedicated, signature-validating public route before enabling it.

## Custom domain

Once the generated HTTPS URL passes the checks above, add a domain in the **web** service's Custom Domains settings, then copy Render's exact DNS records into your domain provider. Wait for DNS verification and the TLS certificate. Keep the API private. Domain purchase and DNS credentials are separate from this repository.

Reference: [Blueprint fields](https://render.com/docs/blueprint-spec), [private services](https://render.com/docs/private-services), [Docker builds](https://render.com/docs/docker), [persistent disks](https://render.com/docs/disks), [custom domains](https://render.com/docs/custom-domains).
