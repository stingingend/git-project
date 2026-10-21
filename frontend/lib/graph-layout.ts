import type { DependencyGraph } from "./types";

export const GRAPH_WIDTH = 760;
export const NODE_WIDTH = 194;
export const NODE_HEIGHT = 72;

export function layoutGraph(graph: DependencyGraph) {
  const incoming = new Set(graph.edges.filter(edge => edge.target === graph.file_id).map(edge => edge.source));
  const outgoing = new Set(graph.edges.filter(edge => edge.source === graph.file_id).map(edge => edge.target));
  const left = graph.nodes.filter(node => node.id !== graph.file_id && !outgoing.has(node.id));
  const right = graph.nodes.filter(node => node.id !== graph.file_id && outgoing.has(node.id));
  const height = Math.max(250, Math.max(left.length, right.length) * 92 + 100);
  const positions = new Map<number, { x: number; y: number }>();
  positions.set(graph.file_id, { x: 283, y: (height - NODE_HEIGHT) / 2 });
  for (const [nodes, x] of [[left, 14], [right, 552]] as const) {
    nodes.forEach((node, index) => positions.set(node.id, { x, y: 64 + index * 92 }));
  }
  const edges = graph.edges.flatMap(edge => {
    const source = positions.get(edge.source), target = positions.get(edge.target);
    if (!source || !target || edge.source === edge.target) return [];
    const reverse = graph.edges.some(other => other.source === edge.target && other.target === edge.source);
    const offset = reverse ? (edge.source === graph.file_id ? 9 : -9) : 0;
    const x1 = source.x + (source.x < target.x ? NODE_WIDTH : 0);
    const x2 = target.x + (source.x < target.x ? 0 : NODE_WIDTH);
    const y1 = source.y + NODE_HEIGHT / 2 + offset;
    const y2 = target.y + NODE_HEIGHT / 2 + offset;
    const mid = (x1 + x2) / 2;
    return [{ ...edge, path: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`,
      labelX: mid, labelY: (y1 + y2) / 2 - 5 }];
  });
  return { height, positions, edges, incoming, outgoing };
}
