import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, createApi, indexRepository } from "../lib/api.ts";

const repository = {
  id: 7,
  owner: "pallets",
  name: "itsdangerous",
  github_url: "https://github.com/pallets/itsdangerous",
  status: "registered",
  created_at: "2026-10-21T00:00:00Z",
};
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

test("indexes in order and reports real stages", async () => {
  const requests = [];
  const stages = [];
  const api = createApi(async (path, options) => {
    requests.push([path, options.method]);
    if (path === "/api/repositories") {
      assert.deepEqual(JSON.parse(options.body), {
        github_url: repository.github_url,
      });
      return json(repository, 201);
    }
    return json({});
  });
  assert.deepEqual(
    await indexRepository(repository.github_url, api, (stage) =>
      stages.push(stage),
    ),
    repository,
  );
  assert.deepEqual(requests, [
    ["/api/repositories", "POST"],
    ["/api/repositories/7/ingest", "POST"],
    ["/api/repositories/7/parse", "POST"],
  ]);
  assert.deepEqual(stages, ["registering", "ingesting", "parsing"]);
});

test("reuses an existing canonical repository after duplicate registration", async () => {
  const requests = [];
  const api = createApi(async (path, options) => {
    requests.push(path);
    if (path === "/api/repositories" && options.method === "POST")
      return json({ detail: "Already registered" }, 409);
    if (path === "/api/repositories") return json([repository]);
    return json({});
  });
  const result = await indexRepository(
    " https://github.com/Pallets/ItsDangerous.git/ ",
    api,
    () => {},
  );
  assert.equal(result.id, 7);
  assert.deepEqual(requests, [
    "/api/repositories",
    "/api/repositories",
    "/api/repositories/7/ingest",
    "/api/repositories/7/parse",
  ]);
});

test("does not parse after failed ingestion", async () => {
  const requests = [];
  const api = createApi(async (path) => {
    requests.push(path);
    return path === "/api/repositories"
      ? json(repository, 201)
      : json({ detail: "Clone exceeded its time limit." }, 422);
  });
  await assert.rejects(
    indexRepository(repository.github_url, api, () => {}),
    /Clone exceeded its time limit/,
  );
  assert.deepEqual(requests, [
    "/api/repositories",
    "/api/repositories/7/ingest",
  ]);
});

test("registration validation stops the workflow and formats Pydantic errors", async () => {
  let requests = 0;
  const api = createApi(async () => {
    requests++;
    return json(
      {
        detail: [
          {
            msg: "Use a repository URL such as https://github.com/pallets/flask.",
          },
        ],
      },
      422,
    );
  });
  await assert.rejects(
    indexRepository("https://example.com/repo", api, () => {}),
    /Use a repository URL/,
  );
  assert.equal(requests, 1);
});

test("does not silently reuse a different repository after a conflict", async () => {
  const api = createApi(async (path, options) =>
    options.method === "POST" ? json({ detail: "Conflict" }, 409) : json([]),
  );
  await assert.rejects(
    indexRepository(repository.github_url, api, () => {}),
    (error) => error instanceof ApiError && error.status === 409,
  );
});

test("reports parse failures after source has been collected", async () => {
  const stages = [];
  const api = createApi(async (path) =>
    path === "/api/repositories"
      ? json(repository, 201)
      : path.endsWith("/ingest")
        ? json({})
        : json({ detail: "Symbol limit reached." }, 422),
  );
  await assert.rejects(
    indexRepository(repository.github_url, api, (stage) => stages.push(stage)),
    /Symbol limit reached/,
  );
  assert.deepEqual(stages, ["registering", "ingesting", "parsing"]);
});

test("handles disconnected and non-JSON backend responses", async () => {
  await assert.rejects(
    createApi(async () => {
      throw new Error("offline");
    }).repositories(),
    /Cannot reach CodeAtlas/,
  );
  await assert.rejects(
    createApi(
      async () => new Response("Bad gateway", { status: 502 }),
    ).repositories(),
    (error) => error instanceof ApiError && error.status === 502,
  );
  await assert.rejects(
    createApi(async () => new Response("invalid")).repositories(),
    /unreadable response/,
  );
});

test("file requests include repository, file ID, and symbol offset", async () => {
  const api = createApi(async (path) => {
    assert.equal(path, "/api/repositories/7/files/19?limit=100&offset=100");
    return json({ symbols: { items: [], offset: 100 } });
  });
  assert.equal((await api.file(7, 19, 100)).symbols.offset, 100);
});
