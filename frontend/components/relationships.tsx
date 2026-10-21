"use client";

import { useEffect, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, GitBranch } from "lucide-react";
import { createApi } from "../lib/api";
import type { RelationshipPage } from "../lib/types";

const api = createApi();

export function Relationships({ repositoryId, fileId, filePath, commitSha, busy, openFile }: {
  repositoryId: number;
  fileId: number;
  filePath: string;
  commitSha: string;
  busy: boolean;
  openFile: (id: number) => void;
}) {
  const [kind, setKind] = useState("imports");
  const [direction, setDirection] = useState("outgoing");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<RelationshipPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setPage(null);
    setError("");
    api.relationships(repositoryId, fileId, kind, direction, offset).then((result) => {
      if (!active) return;
      if (result.ready && result.commit_sha !== commitSha) {
        setError("The index changed. Refresh the repository to view its relationships.");
      } else setPage(result);
    }).catch((reason) => { if (active) setError(String(reason.message)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [repositoryId, fileId, commitSha, kind, direction, offset]);
  return <section className="relationships" aria-label="File relationships">
    <div className="relationship-heading"><h3><GitBranch size={15} /> File relationships</h3>
      <span>{filePath}</span></div>
    <div className="relationship-controls">
      <select aria-label="Relationship type" value={kind} disabled={busy} onChange={(event) => {
        setKind(event.target.value); setDirection("outgoing"); setOffset(0);
      }}><option value="imports">Imports</option><option value="contains">Containment</option></select>
      {kind === "imports" && <select aria-label="Relationship direction" value={direction} disabled={busy}
        onChange={(event) => { setDirection(event.target.value); setOffset(0); }}>
        <option value="outgoing">Imports from this file</option><option value="incoming">Files importing this file</option>
      </select>}
    </div>
    <p className="relationship-help">{kind === "imports"
      ? "Local links resolve to saved files. Unresolved imports may be external, dynamic, or outside supported layouts."
      : "Each arrow connects a file or definition to a directly enclosed symbol."}</p>
    {error && <p role="alert" className="inline-notice">{error}</p>}
    {loading && <p role="status" className="relationship-help">Loading relationships…</p>}
    {page && !page.ready && <p className="inline-notice">Re-index this repository to build relationships.</p>}
    {page?.ready && <>
      <div className="relationship-list">
        {page.items.map((edge) => <div className="relationship-row" key={edge.id}>
          <div><strong>{direction === "incoming" ? edge.path : edge.source_name}</strong>
            <ArrowRight size={12} /><span>{edge.target_name}</span></div>
          <small>L{edge.start_line} · {edge.resolution}</small>
          {edge.target_file_id !== null && direction === "outgoing" &&
            <button disabled={busy} onClick={() => openFile(edge.target_file_id!)}>Open dependency</button>}
          {direction === "incoming" &&
            <button disabled={busy} onClick={() => openFile(edge.file_id)}>Open importer</button>}
        </div>)}
        {!page.items.length && <p className="relationship-help">No relationships in this view.</p>}
      </div>
      <div className="viewer-footer"><span>{page.total} relationships · {commitSha.slice(0, 7)}</span><div>
        <button aria-label="Previous relationship page" disabled={busy || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 30))}><ChevronLeft size={14} /></button>
        <span>{page.items.length ? `${offset + 1}–${offset + page.items.length}` : "0"}</span>
        <button aria-label="Next relationship page" disabled={busy || offset + 30 >= page.total}
          onClick={() => setOffset(offset + 30)}><ChevronRight size={14} /></button>
      </div></div>
    </>}
  </section>;
}
