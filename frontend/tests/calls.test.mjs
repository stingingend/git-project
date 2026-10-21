import assert from "node:assert/strict";
import { test } from "node:test";
import { createApi } from "../lib/api.ts";

test("call requests include scope, resolution filter, and page offset", async () => {
  const api = createApi(async path => {
    const url = new URL(path, "http://localhost");
    assert.equal(url.pathname, "/api/repositories/3/files/9/calls");
    assert.equal(url.searchParams.get("resolution"), "candidate");
    assert.equal(url.searchParams.get("offset"), "30");
    assert.equal(url.searchParams.get("limit"), "30");
    return new Response(JSON.stringify({ items: [], total: 0 }));
  });
  await api.calls(3, 9, "candidate", 30);
});

test("unfiltered call pages omit the optional resolution parameter", async () => {
  const api = createApi(async path => {
    assert.equal(new URL(path, "http://localhost").searchParams.has("resolution"), false);
    return new Response(JSON.stringify({ items: [], ready: false }));
  });
  assert.equal((await api.calls(3, 9)).ready, false);
});
