import assert from "node:assert/strict";
import { test } from "node:test";
import { frameEdges, graphFrame, transitionFrame } from "../lib/graph-motion.ts";

const first = graphFrame({ file_id: 1, nodes: [{ id: 1, path: "a.py" }, { id: 2, path: "b.py" }, { id: 3, path: "old.py" }],
  edges: [{ source: 1, target: 2, count: 2 }, { source: 3, target: 1, count: 1 }] });
const second = graphFrame({ file_id: 2, nodes: [{ id: 1, path: "a.py" }, { id: 2, path: "b.py" }, { id: 4, path: "new.py" }],
  edges: [{ source: 1, target: 2, count: 2 }, { source: 2, target: 4, count: 1 }] });

test("shared nodes keep identity and interpolate from their actual previous coordinates", () => {
  const frame = transitionFrame(first, second, 0.5);
  for (const id of [1, 2]) {
    const before = first.nodes.find(node => node.id === id);
    const after = second.nodes.find(node => node.id === id);
    const node = frame.nodes.find(node => node.id === id);
    assert.equal(node.x, (before.x + after.x) / 2);
    assert.equal(node.y, (before.y + after.y) / 2);
    assert.equal(node.opacity, 1);
  }
  assert.equal(frame.nodes.find(node => node.id === 3).opacity, 0.5);
  assert.equal(frame.nodes.find(node => node.id === 4).opacity, 0.5);
  assert.deepEqual(transitionFrame(first, second, 1), second);
});

test("interrupted navigation resumes from the current animated frame", () => {
  const partial = transitionFrame(first, second, 0.3);
  const resumed = transitionFrame(partial, first, 0);
  for (const node of partial.nodes) {
    const current = resumed.nodes.find(item => item.id === node.id);
    assert.equal(current.x, node.x);
    assert.equal(current.y, node.y);
    assert.equal(current.opacity, node.opacity);
  }
});

test("arrows attach to moving card boundaries and departing links fade", () => {
  const frame = transitionFrame(first, second, 0.5);
  const edge = frameEdges(frame).find(edge => edge.source === 1 && edge.target === 2);
  const source = frame.nodes.find(node => node.id === 1);
  const target = frame.nodes.find(node => node.id === 2);
  const x = source.x + (source.x < target.x ? 194 : 0);
  assert.ok(edge.path.startsWith(`M ${x} ${source.y + 36}`));
  assert.equal(frame.edges.find(edge => edge.source === 3).opacity, 0.5);
  assert.equal(frame.edges.find(edge => edge.target === 4).opacity, 0.5);
});

test("first render fades nodes from the center and completed frames discard exiting nodes", () => {
  const start = transitionFrame(null, first, 0);
  assert.ok(start.nodes.every(node => node.opacity === 0));
  assert.deepEqual(transitionFrame(first, second, 1).nodes.map(node => node.id), [1, 2, 4]);
  assert.equal(frameEdges(second).length, 2);
});
