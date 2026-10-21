import assert from "node:assert/strict";
import { test } from "node:test";
import { activeJob, createApi, startIndexJob } from "../lib/api.ts";

const repo = { id: 7, github_url: "https://github.com/example/demo" };
const job = { id: "durable-job", repository_id: 7, status: "queued", stage: "queued" };
const json = body => new Response(JSON.stringify(body));

test("background indexing registers and submits without synchronous ingestion or parsing", async () => {
  const paths = [];
  const api = createApi(async (path, options) => {
    paths.push(path);
    assert.equal(options.method, "POST");
    return json(path === "/api/repositories" ? repo : job);
  });
  assert.deepEqual(await startIndexJob(repo.github_url, api), { repository: repo, job });
  assert.deepEqual(paths, ["/api/repositories", "/api/repositories/7/jobs"]);
});

test("existing repositories reconnect to a durable job", async () => {
  const api = createApi(async (path, options) => {
    if (path === "/api/repositories" && options.method === "POST") {
      return new Response(JSON.stringify({ detail: "Already registered" }), { status: 409 });
    }
    if (path === "/api/repositories") return json([repo]);
    assert.equal(path, "/api/repositories/7/jobs");
    return json({ ...job, status: "running" });
  });
  assert.equal((await startIndexJob("https://github.com/EXAMPLE/demo.git", api)).job.status, "running");
});

test("job polling and recent history use separate read endpoints", async () => {
  const paths = [];
  const api = createApi(async path => { paths.push(path); return json(job); });
  await api.job("id/with spaces");
  await api.jobs();
  assert.deepEqual(paths, ["/api/jobs/id%2Fwith%20spaces", "/api/jobs?limit=10"]);
  for (const status of ["queued", "running"]) assert.ok(activeJob({ status }));
  for (const status of ["succeeded", "failed", "interrupted"]) assert.equal(activeJob({ status }), false);
});
