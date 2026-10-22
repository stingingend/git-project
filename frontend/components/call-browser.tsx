"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { createApi } from "../lib/api";
import type { CallPage, SymbolRecord } from "../lib/types";

const api = createApi();

export function CallBrowser({ repositoryId, fileId, commitSha, githubUrl, language, busy, selectSymbol }: {
  repositoryId: number; fileId: number; commitSha: string; githubUrl: string;
  language: string;
  busy: boolean; selectSymbol: (symbol: SymbolRecord) => void;
}) {
  const [page, setPage] = useState<CallPage | null>(null);
  const [resolution, setResolution] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setPage(null);
    api.calls(repositoryId, fileId, resolution, offset).then(result => {
      if (!active) return;
      if (result.file_id !== fileId || (result.ready && result.commit_sha !== commitSha)) {
        setError("The index changed. Refresh the repository to view call sites.");
      } else setPage(result);
    }).catch(reason => { if (active) setError(String(reason.message)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [repositoryId, fileId, commitSha, resolution, offset]);
  return <>
    <div className="call-intro">
      <strong>Call sites <span>Approximate analysis</span></strong>
      <p>{language === "Python"
        ? "Possible targets use lexical scope, explicit imports, and self/cls methods. Aliases, assignments, parameters, and runtime behavior can change the actual target."
        : ["C", "C++"].includes(language)
        ? "Possible targets use same-file definitions. Overloads can be ambiguous; cross-file calls, function pointers, macros, and virtual dispatch are not resolved."
        : "Possible targets use same-file lexical scope and direct this.method calls. Imported calls, arbitrary receiver types, and runtime rebinding remain unresolved."}</p>
      <label>Show <select aria-label="Filter call resolution" value={resolution} disabled={busy}
        onChange={event => { setResolution(event.target.value); setOffset(0); }}>
        <option value="">All calls</option><option value="candidate">Possible targets</option>
        <option value="ambiguous">Ambiguous</option><option value="unresolved">Unresolved</option>
      </select></label>
      {page?.ready && <small>{page.summary.total} calls · {page.summary.candidates} possible targets · {page.summary.ambiguous} ambiguous · {page.summary.unresolved} unresolved</small>}
    </div>
    <div className="call-list" role="tabpanel" aria-label="File call sites" tabIndex={0}>
      {loading && <p className="panel-empty" role="status">Loading call sites…</p>}
      {error && <p className="panel-empty" role="alert">{error}</p>}
      {page && !page.ready && <p className="panel-empty">Re-index this repository to extract call sites.</p>}
      {page?.ready && page.items.map(call => <article className="call-row" key={call.id}>
        <div><code title={call.expression}>{call.expression}(…)</code>
          <a href={`${githubUrl}#L${call.start_line}-L${call.end_line}`} target="_blank" rel="noreferrer"
            aria-label={`View call at line ${call.start_line} column ${call.column} on GitHub`}>L{call.start_line}:{call.column} <ExternalLink size={11} /></a></div>
        <small>Enclosed by {call.caller?.name ?? "module"} · {call.call_type}</small>
        {call.target ? <button className="call-target" disabled={busy || loading} onClick={() => selectSymbol(call.target!)}>
          <ArrowUpRight size={13} /> Possible target: {call.target.name} <span>L{call.target.start_line}</span>
        </button> : <span className="call-resolution">{call.resolution === "ambiguous" ? "Multiple definitions match" : "No target suggested"}</span>}
      </article>)}
      {page?.ready && page.items.length === 0 && <p className="panel-empty">No call sites in this view.</p>}
    </div>
    <div className="viewer-footer"><span>{page?.ready ? `${page.total} matching call sites` : "Call analysis"}</span><div>
      <button aria-label="Previous call page" disabled={busy || loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}><ChevronLeft size={14} /></button>
      <span>{page?.items.length ? `${offset + 1}–${offset + page.items.length}` : "0"}</span>
      <button aria-label="Next call page" disabled={busy || loading || !page || offset + 30 >= page.total} onClick={() => setOffset(offset + 30)}><ChevronRight size={14} /></button>
    </div></div>
  </>;
}
