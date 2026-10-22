"use client";
import { useState } from "react";
import { GitBranch, LoaderCircle } from "lucide-react";
import { createApi } from "../lib/api";
import type { ArchitectureReport, ImpactReport, SearchHit, SourceFile, SymbolRecord } from "../lib/types";

const api = createApi();
export function AnalysisPanel({ repositoryId, commitSha, files, busy, selectedSymbol, selectFile, selectSymbol }: {
  repositoryId: number; commitSha: string; files: SourceFile[]; busy: boolean;
  selectedSymbol?: SymbolRecord; selectFile: (fileId: number) => void; selectSymbol: (hit: SearchHit, commit: string) => void;
}) {
  const [mode, setMode] = useState<"impact" | "architecture">("impact");
  const [fileId, setFileId] = useState(files[0]?.id ?? 0);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [architecture, setArchitecture] = useState<ArchitectureReport | null>(null);
  async function analyze(symbol = false) {
    setWorking(true); setError("");
    try {
      const report = mode === "architecture" ? await api.architecture(repositoryId)
        : await api.impact(repositoryId, symbol ? [] : [fileId], symbol && selectedSymbol ? [selectedSymbol.id] : []);
      if (report.commit_sha !== commitSha) throw new Error("The index changed. Refresh this repository.");
      if (mode === "architecture") setArchitecture(report as ArchitectureReport);
      else setImpact(report as ImpactReport);
    } catch (reason) { setError((reason as Error).message); }
    finally { setWorking(false); }
  }
  const disabled = busy || working;
  return <details className="intelligence-panel analysis-panel">
    <summary><GitBranch size={18} /> Impact & architecture <span>Trace dependencies and find structural hotspots</span></summary>
    <div className="intelligence-tabs" role="group" aria-label="Analysis mode">
      <button aria-pressed={mode === "impact"} onClick={() => setMode("impact")} disabled={working}>Change impact</button>
      <button aria-pressed={mode === "architecture"} onClick={() => setMode("architecture")} disabled={working}>Architecture metrics</button>
    </div>
    {mode === "impact" ? <>
      <p className="intelligence-note">Follow reverse imports and approximate callers. Potential impact is not a guarantee that code will break.</p>
      <div className="intelligence-query"><select aria-label="File to analyze" value={fileId} onChange={event => setFileId(Number(event.target.value))} disabled={disabled}>
        {files.map(file => <option key={file.id} value={file.id}>{file.path}</option>)}</select>
        <button disabled={disabled || !fileId} onClick={() => void analyze()}>{working && <LoaderCircle size={14} className="spin" />} Analyze file impact</button>
        {selectedSymbol && <button disabled={disabled} onClick={() => void analyze(true)}>Analyze selected symbol: {selectedSymbol.name}</button>}
      </div>
      {impact && <div className="analysis-results">
        <div className="analysis-stats"><span><strong>{impact.affected_file_count}</strong> dependent files</span>
          <span><strong>{impact.affected_symbol_count}</strong> possible callers</span><span><strong>{impact.scope}</strong> scope</span></div>
        <p className="intelligence-note">{impact.scope_rule}</p>
        {impact.truncated && <p className="notice">The report reached a depth or result limit; more dependents may exist.</p>}
        <p className="intelligence-note">{impact.unresolved_imports} unresolved imports · {impact.unresolved_calls} unresolved/ambiguous calls in this repository.</p>
        <div className="analysis-list">{impact.files.map(file => <button disabled={disabled} key={file.file_id} onClick={() => selectFile(file.file_id)}>
          {file.path}<small>{file.is_test ? "Test · " : ""}{file.depth === 1 ? "Direct dependency" : `${file.depth} steps away`}</small></button>)}</div>
        {impact.files.length === 0 && <p>No dependent files found in the resolved graph.</p>}
        {impact.symbols.length > 0 && <details><summary>Inspect possible callers</summary><div className="analysis-list">
          {impact.symbols.map(hit => <button key={hit.symbol.id} disabled={disabled} onClick={() => selectSymbol({...hit, has_parse_errors: false}, impact.commit_sha)}>
            {hit.symbol.qualified_name}<small>{hit.depth} call steps</small></button>)}
        </div></details>}
      </div>}
    </> : <>
      <p className="intelligence-note">Resolved file imports · PageRank centrality · strongly connected cycle groups.</p>
      <button disabled={disabled} onClick={() => void analyze()}>{working && <LoaderCircle size={14} className="spin" />} Calculate architecture metrics</button>
      {architecture && <div className="analysis-results">
        <div className="analysis-stats"><span><strong>{architecture.dependency_pairs}</strong> dependency pairs</span>
          <span><strong>{architecture.cycle_component_count}</strong> cycle groups</span><span><strong>{architecture.isolated_files}</strong> isolated files</span></div>
        <div className="analysis-table-wrap"><table><caption>Architectural hubs · top {architecture.hubs.length}</caption>
          <thead><tr><th>File</th><th>Fan-in</th><th>Fan-out</th><th>Centrality</th><th>Branches</th></tr></thead>
          <tbody>{architecture.hubs.map(file => <tr key={file.file_id}><td><button disabled={disabled} onClick={() => selectFile(file.file_id)}>{file.path}</button></td>
            <td>{file.fan_in}</td><td>{file.fan_out}</td><td>{file.centrality.toFixed(4)}</td><td>{file.branch_points ?? "—"}</td></tr>)}</tbody>
        </table></div>
        {architecture.cycles.map((group, index) => <div className="cycle-group" key={index}><strong>Cycle group {index + 1} · {group.size} files</strong>
          <div className="analysis-list">{group.files.map(file => <button key={file.file_id} disabled={disabled} onClick={() => selectFile(file.file_id)}>{file.path}</button>)}</div>
          {group.truncated && <small>Only the first 50 files shown.</small>}</div>)}
        <details><summary>Coupling and branch hotspots</summary><p className="intelligence-note">{architecture.hotspot_rule}</p>
          <div className="analysis-list">{architecture.hotspots.slice(0, 10).map(file => <button key={file.file_id} onClick={() => selectFile(file.file_id)} disabled={disabled}>
            {file.path}<small>Review score {file.review_score}</small></button>)}</div></details>
        <p className="intelligence-note">{architecture.unresolved_imports} unresolved imports · {architecture.parse_error_files} files requiring parser recovery. Partial analysis may omit dependencies.</p>
      </div>}
    </>}
    {error && <p role="alert" className="intelligence-error">{error}</p>}
  </details>;
}
