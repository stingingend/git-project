import assert from "node:assert/strict";
import { test } from "node:test";
import { createApi } from "../lib/api.ts";

test("semantic queries preserve natural language and scope", async () => {
  const api = createApi(async (url, options) => {
    const parsed = new URL(url, "http://localhost");
    assert.equal(parsed.pathname, "/api/repositories/17/semantic/search");
    assert.equal(parsed.searchParams.get("q"), "tokens + sessions / café?");
    assert.equal(options.cache, "no-store");
    return Response.json({items: []});
  });
  await api.semanticSearch(17, "tokens + sessions / café?");
});

test("questions opt into generation explicitly in a JSON body", async () => {
  const api = createApi(async (url, options) => {
    assert.equal(url, "/api/repositories/8/questions");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {question: 'Where is "auth" handled?', generate: false});
    return Response.json({answer: "Source findings", citations: []});
  });
  await api.ask(8, 'Where is "auth" handled?', false);
});

test("targeted indexing sends an explicit SHA without changing ordinary submissions", async () => {
  const requests = [];
  const api = createApi(async (url, options) => { requests.push({url, options}); return Response.json({id: "job"}); });
  await api.startJob(3);
  await api.startJob(3, "a".repeat(40));
  assert.equal(requests[0].options.body, undefined);
  assert.deepEqual(JSON.parse(requests[1].options.body), {commit_sha: "a".repeat(40)});
});
