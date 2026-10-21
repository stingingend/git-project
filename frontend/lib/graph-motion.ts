import type { DependencyGraph } from "./types";
import { layoutGraph, NODE_HEIGHT, NODE_WIDTH } from "./graph-layout.ts";

export type MotionNode = {
  id: number; path: string; x: number; y: number; opacity: number;
  center: boolean; relation: string;
};
export type MotionEdge = { source: number; target: number; count: number; opacity: number };
export type GraphFrame = { nodes: MotionNode[]; edges: MotionEdge[]; height: number };

export function graphFrame(graph: DependencyGraph): GraphFrame {
  const layout = layoutGraph(graph);
  return {
    height: layout.height,
    nodes: graph.nodes.map(node => ({ ...node, ...layout.positions.get(node.id)!, opacity: 1,
      center: node.id === graph.file_id,
      relation: layout.incoming.has(node.id) && layout.outgoing.has(node.id) ? "Imports in both directions"
        : layout.outgoing.has(node.id) ? "Imported by selected file" : "Imports selected file" })),
    edges: graph.edges.map(edge => ({ ...edge, opacity: 1 })),
  };
}

const edgeKey = (edge: MotionEdge) => `${edge.source}:${edge.target}`;
const mix = (from: number, to: number, progress: number) => from + (to - from) * progress;

export function transitionFrame(previous: GraphFrame | null, target: GraphFrame, progress: number): GraphFrame {
  if (progress >= 1) return target;
  const before = new Map(previous?.nodes.map(node => [node.id, node]) ?? []);
  const after = new Map(target.nodes.map(node => [node.id, node]));
  const origin = previous?.nodes.find(node => node.center) ?? target.nodes.find(node => node.center)!;
  const destination = target.nodes.find(node => node.center)!;
  const nodes = [...new Set([...before.keys(), ...after.keys()])].map(id => {
    const old = before.get(id), next = after.get(id);
    const from = old ?? { ...next!, x: origin.x, y: origin.y, opacity: 0 };
    const to = next ?? { ...old!, x: destination.x, y: destination.y, opacity: 0 };
    return { ...to, x: mix(from.x, to.x, progress), y: mix(from.y, to.y, progress),
      opacity: mix(from.opacity, to.opacity, progress) };
  });
  const oldEdges = new Map(previous?.edges.map(edge => [edgeKey(edge), edge]) ?? []);
  const newEdges = new Map(target.edges.map(edge => [edgeKey(edge), edge]));
  const edges = [...new Set([...oldEdges.keys(), ...newEdges.keys()])].map(key => {
    const old = oldEdges.get(key), next = newEdges.get(key);
    return { ...(next ?? old!), opacity: mix(old?.opacity ?? 0, next?.opacity ?? 0, progress) };
  });
  return { nodes, edges, height: mix(previous?.height ?? target.height, target.height, progress) };
}

// Both cards and SVG endpoints use this same interpolated frame.
export function frameEdges(frame: GraphFrame) {
  const positions = new Map(frame.nodes.map(node => [node.id, node]));
  return frame.edges.flatMap(edge => {
    const source = positions.get(edge.source), target = positions.get(edge.target);
    if (!source || !target || source.id === target.id) return [];
    const reverse = frame.edges.some(other => other.source === edge.target && other.target === edge.source);
    const offset = reverse ? (source.center ? 9 : -9) : 0;
    const x1 = source.x + (source.x < target.x ? NODE_WIDTH : 0);
    const x2 = target.x + (source.x < target.x ? 0 : NODE_WIDTH);
    const y1 = source.y + NODE_HEIGHT / 2 + offset, y2 = target.y + NODE_HEIGHT / 2 + offset;
    const mid = (x1 + x2) / 2;
    return [{ ...edge, path: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`,
      labelX: mid, labelY: (y1 + y2) / 2 - 5 }];
  });
}
