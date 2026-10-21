import assert from "node:assert/strict";
import { test } from "node:test";
import { createApi, loadSymbolSource } from "../lib/api.ts";
import { isSelectedLine, pageForLine } from "../lib/source-range.ts";

const symbol = {
  id: 12,
  file_id: 8,
  name: "sign",
  qualified_name: "src/signer.py::Signer.sign",
  signature: "def sign(self)",
  symbol_type: "method",
  start_line: 222,
  end_line: 225,
};
const hit = { symbol, path: "src/signer.py", has_parse_errors: false };
const sha = "a".repeat(40);
const json = (body) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
const selected = { symbol, file: { id: 8, path: hit.path }, commit_sha: sha };
const detail = {
  file: { id: 8, path: hit.path },
  commit_sha: sha,
  source: "saved source",
};

test("search parameters preserve literal text, type, and offset", async () => {
  const api = createApi(async (path) => {
    const url = new URL(path, "http://localhost");
    assert.equal(url.pathname, "/api/repositories/7/search");
    assert.equal(url.searchParams.get("q"), "src/a_100% café");
    assert.equal(url.searchParams.get("kind"), "method");
    assert.equal(url.searchParams.get("offset"), "20");
    assert.equal(url.searchParams.get("limit"), "20");
    return json({ items: [], total: 0 });
  });
  await api.search(7, "src/a_100% café", "method", 20);
});

test("symbol selection validates identity and loads the file containing it", async () => {
  const requests = [];
  const api = createApi(async (path) => {
    requests.push(path);
    return json(path.includes("/symbols/") ? selected : detail);
  });
  const loaded = await loadSymbolSource(api, 7, hit, sha);
  assert.deepEqual(loaded, { detail, symbol, commit_sha: sha });
  assert.deepEqual(requests, [
    "/api/repositories/7/symbols/12",
    "/api/repositories/7/files/8?limit=100&offset=0",
  ]);
});

test("rejects a stale commit without fetching another file", async () => {
  let count = 0;
  const api = createApi(async () => {
    count++;
    return json({ ...selected, commit_sha: "b".repeat(40) });
  });
  await assert.rejects(loadSymbolSource(api, 7, hit, sha), /index changed/);
  assert.equal(count, 1);
});

test("rejects a reused symbol ID that now points at a different definition", async () => {
  const api = createApi(async () =>
    json({
      ...selected,
      symbol: { ...symbol, qualified_name: "other.py::unrelated" },
    }),
  );
  await assert.rejects(loadSymbolSource(api, 7, hit, sha), /index changed/);
});

test("rejects source replaced between symbol and file requests", async () => {
  const api = createApi(async (path) =>
    json(
      path.includes("/symbols/")
        ? selected
        : { ...detail, commit_sha: "b".repeat(40) },
    ),
  );
  await assert.rejects(loadSymbolSource(api, 7, hit, sha), /index changed/);
});

test("definition line selects the correct source page", () => {
  for (const [line, page] of [
    [1, 0],
    [200, 0],
    [201, 1],
    [222, 1],
    [400, 1],
    [401, 2],
  ]) {
    assert.equal(pageForLine(line), page);
  }
});

test("source highlighting uses inclusive bounds across pages", () => {
  assert.equal(isSelectedLine(221, 222, 401), false);
  assert.equal(isSelectedLine(222, 222, 401), true);
  assert.equal(isSelectedLine(400, 222, 401), true);
  assert.equal(isSelectedLine(401, 222, 401), true);
  assert.equal(isSelectedLine(402, 222, 401), false);
});
