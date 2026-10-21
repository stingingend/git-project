import assert from "node:assert/strict";
import { test } from "node:test";
import { createApi } from "../lib/api.ts";
import { layoutGraph, NODE_HEIGHT, NODE_WIDTH } from "../lib/graph-layout.ts";

const graph = { file_id: 1, nodes: [{ id: 1, path: "center.py" }, { id: 2, path: "in.py" }, { id: 3, path: "out.py" }],
  edges: [{ source: 2, target: 1, count: 1 }, { source: 1, target: 3, count: 3 }, { source: 3, target: 1, count: 1 }] };

test("graph lays importers left, dependencies right, and preserves reverse arrows", () => {
  const layout = layoutGraph(graph);
  assert.ok(layout.positions.get(2).x < layout.positions.get(1).x);
  assert.ok(layout.positions.get(3).x > layout.positions.get(1).x);
  assert.equal(layout.edges.length, 3);
  assert.notEqual(layout.edges[1].path, layout.edges[2].path);
  assert.equal(layout.edges[1].count, 3);
  for (const position of layout.positions.values()) {
    assert.ok(position.y >= 0 && position.y + NODE_HEIGHT <= layout.height);
    assert.ok(position.x >= 0 && position.x + NODE_WIDTH <= 760);
  }
});

test("large neighborhoods allocate separate rows and empty graphs keep a center", () => {
  const nodes = [{ id: 1, path: "center.py" }, ...Array.from({ length: 12 }, (_, index) => ({ id: index + 2, path: `${index}.py` }))];
  const layout = layoutGraph({ file_id: 1, nodes, edges: nodes.slice(1).map(node => ({ source: node.id, target: 1, count: 1 })) });
  const positions = nodes.slice(1).map(node => layout.positions.get(node.id).y);
  assert.equal(new Set(positions).size, 12);
  assert.ok(Math.max(...positions) + NODE_HEIGHT < layout.height);
  const empty = layoutGraph({ file_id: 1, nodes: [nodes[0]], edges: [] });
  assert.equal(empty.positions.size, 1);
  assert.deepEqual(empty.edges, []);
});

test("graph API scopes requests by repository and file", async () => {
  const api = createApi(async path => {
    assert.equal(path, "/api/repositories/7/files/11/graph");
    return new Response(JSON.stringify({ nodes: [], edges: [] }));
  });
  assert.deepEqual(await api.graph(7, 11), { nodes: [], edges: [] });
});
