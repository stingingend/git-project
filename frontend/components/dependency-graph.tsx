"use client";

import { useEffect, useId, useState } from "react";
import { FileCode2, Network, RefreshCw } from "lucide-react";
import { createApi } from "../lib/api";
import { GRAPH_WIDTH, NODE_HEIGHT, NODE_WIDTH, layoutGraph } from "../lib/graph-layout";
import type { DependencyGraph as Graph } from "../lib/types";

const api = createApi();

export function DependencyGraph({ repositoryId, fileId, filePath, commitSha, busy, openFile }: {
  repositoryId: number; fileId: number; filePath: string; commitSha: string;
  busy: boolean; openFile: (id: number) => void;
}) {
  const marker = useId().replace(/:/g, "");
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setGraph(null); setError(""); setLoading(true);
    api.graph(repositoryId, fileId).then(result => {
      if (!active) return;
      const center = result.nodes.find(node => node.id === fileId);
      if (result.file_id !== fileId || center?.path !== filePath ||
          (result.ready && result.commit_sha !== commitSha)) {
        setError("The index changed. Refresh the repository to view its graph.");
      } else setGraph(result);
    }).catch(reason => { if (active) setError(String(reason.message)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [repositoryId, fileId, filePath, commitSha, attempt]);
  const layout = graph ? layoutGraph(graph) : null;
  return <section className="dependency-graph" aria-label="File dependency graph">
    <div className="graph-heading">
      <div><span className="graph-icon"><Network size={20} /></span><div>
        <h3>Explore the connections</h3><p>One file. Its direct Python dependencies.</p>
      </div></div>
      <button className="secondary" disabled={busy || loading} onClick={() => setAttempt(attempt + 1)}>
        <RefreshCw size={13} /> Reload graph
      </button>
    </div>
    <div className="graph-legend"><span><i /> Selected file</span><span>Arrow direction: importer → dependency</span></div>
    {loading && <p className="graph-message" role="status">Loading dependency graph…</p>}
    {error && <p className="graph-message" role="alert">{error}</p>}
    {graph && !graph.ready && <p className="graph-message">Re-index this repository to build its dependency graph.</p>}
    {graph?.ready && layout && <>
      {graph.total_neighbors === 0 && <p className="graph-message">No resolved local dependencies connect to this file.</p>}
      <div className="graph-scroll" tabIndex={0} aria-label="Dependency diagram. Scroll to explore connected files.">
        <div className="graph-canvas" style={{ height: layout.height }}>
          <span className="graph-column-label" style={{ left: `${14 / GRAPH_WIDTH * 100}%` }}>IMPORTERS</span>
          <span className="graph-column-label" style={{ left: `${283 / GRAPH_WIDTH * 100}%` }}>SELECTED FILE</span>
          <span className="graph-column-label" style={{ left: `${552 / GRAPH_WIDTH * 100}%` }}>DEPENDENCIES</span>
          <svg width={GRAPH_WIDTH} height={layout.height} viewBox={`0 0 ${GRAPH_WIDTH} ${layout.height}`} preserveAspectRatio="none" aria-hidden="true">
            <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#7894c5" />
            </marker></defs>
            {layout.edges.map(edge => <g key={`${edge.source}:${edge.target}`}>
              <path d={edge.path} fill="none" stroke="#7894c5" strokeWidth="1.8" markerEnd={`url(#${marker})`} />
              {edge.count > 1 && <text x={edge.labelX} y={edge.labelY} textAnchor="middle">×{edge.count}</text>}
            </g>)}
          </svg>
          {graph.nodes.map(node => {
            const position = layout.positions.get(node.id)!;
            const center = node.id === fileId;
            const relation = layout.incoming.has(node.id) && layout.outgoing.has(node.id) ? "Imports in both directions"
              : layout.outgoing.has(node.id) ? "Imported by selected file" : "Imports selected file";
            const content = <><span><FileCode2 size={15} /><strong>{node.path.split("/").at(-1)}</strong></span>
              <small>{node.path}</small><em>{center ? "You are here" : relation}</em></>;
            const style = { left: `${position.x / GRAPH_WIDTH * 100}%`, top: position.y, width: `${NODE_WIDTH / GRAPH_WIDTH * 100}%`, height: NODE_HEIGHT };
            return center ? <div className="graph-node graph-center" key={node.id} style={style} title={node.path}>{content}</div>
              : <button className="graph-node" key={node.id} style={style} title={node.path}
                  disabled={busy} aria-label={`Open ${node.path}. ${relation}`} onClick={() => openFile(node.id)}>{content}</button>;
          })}
        </div>
      </div>
      <ul className="sr-only" aria-label="Directed dependency links">{graph.edges.map(edge => <li key={`${edge.source}:${edge.target}`}>
        {graph.nodes.find(node => node.id === edge.source)?.path} imports {graph.nodes.find(node => node.id === edge.target)?.path}: {edge.count} import links.
      </li>)}</ul>
      <div className="graph-summary"><span>{graph.nodes.length - 1} of {graph.total_neighbors} connected files · {commitSha.slice(0, 7)}</span>
        <span>{graph.unresolved_imports} unresolved import links{graph.self_imports > 0 ? ` · ${graph.self_imports} self-import links` : ""}</span></div>
      {graph.total_neighbors > graph.nodes.length - 1 && <p className="graph-message">Showing the first 12 connected files by path. Use File relationships below to browse every import link.</p>}
      <p className="graph-footnote">Select a connected file to make it the focus. Repeated import links are combined; external and unresolved targets are excluded. This shows static module dependencies, not function calls.</p>
    </>}
  </section>;
}
