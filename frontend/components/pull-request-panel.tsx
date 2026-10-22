"use client";
import { useEffect, useState } from "react";
import { ExternalLink, GitPullRequest, LoaderCircle } from "lucide-react";
import { ApiError, createApi } from "../lib/api";
import type { PullRequestReport } from "../lib/types";

const api = createApi();
const active = (report: PullRequestReport) => ["queued", "running"].includes(report.status);

export function PullRequestPanel({ repositoryId, commitSha, busy, indexCommit }: {
  repositoryId: number; commitSha: string; busy: boolean; indexCommit: (sha: string) => void;
}) {
  const [number, setNumber] = useState("");
  const [report, setReport] = useState<PullRequestReport | null>(null);
  const [history, setHistory] = useState<PullRequestReport[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    api.pullRequests(repositoryId).then(items => {
      if (current) { setHistory(items); setReport(previous => previous ?? items[0] ?? null); }
    }).catch(reason => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [repositoryId]);
  useEffect(() => {
    if (!report || !active(report)) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const id = report.id;
    async function poll() {
      try {
        const updated = await api.pullRequest(repositoryId, id);
        if (!current) return;
        setReport(updated); setError("");
        setHistory(items => [updated, ...items.filter(item => item.id !== updated.id)].slice(0, 10));
        if (!active(updated)) return;
      } catch (reason) {
        if (!current) return;
        setError((reason as Error).message);
        if (reason instanceof ApiError && reason.status === 404) return;
      }
      if (current) timer = setTimeout(poll, 1500);
    }
    void poll();
    return () => { current = false; clearTimeout(timer); };
  }, [repositoryId, report?.id]);
  async function start(event: React.FormEvent) {
    event.preventDefault(); setStarting(true); setError("");
    try { setReport(await api.startPullRequest(repositoryId, Number(number))); }
    catch (reason) { setError((reason as Error).message); }
    finally { setStarting(false); }
  }
  const running = starting || (report ? active(report) : false);
  const result = report?.result;
  return <details className="intelligence-panel analysis-panel pr-panel">
    <summary><GitPullRequest size={18} /> Public pull request analysis <span>Changed symbols and downstream impact</span></summary>
    <p className="intelligence-note">Read-only reports for this repository. Changed lines map only when the indexed commit matches the PR base.</p>
    <form className="intelligence-query" onSubmit={start}>
      <input aria-label="Pull request number" type="number" min={1} max={10000000} placeholder="PR number, e.g. 42" value={number}
        onChange={event => setNumber(event.target.value)} disabled={busy || running} />
      <button className="primary" disabled={busy || running || !Number.isInteger(Number(number)) || Number(number) < 1}>
        {running ? <LoaderCircle size={14} className="spin" /> : <GitPullRequest size={14} />} Analyze public PR</button>
    </form>
    {report && <p className="intelligence-note">Report {report.id.slice(0, 8)} · PR #{report.number} · {report.status} · saved locally</p>}
    {report?.error && <p role="alert" className="intelligence-error">{report.error}</p>}
    {error && <p role="alert" className="intelligence-error">{error}</p>}
    {result && <div className="analysis-results">
      <h3>#{result.number} · {result.title}</h3>
      <p className="intelligence-note">Base {result.base_sha.slice(0, 7)} → head {result.head_sha.slice(0, 7)} · indexed {result.commit_sha?.slice(0, 7) ?? "none"}</p>
      <a href={result.github_url} target="_blank" rel="noreferrer">View PR on GitHub <ExternalLink size={12} /></a>
      {result.requires_base_index && <div className="notice"><p>Index the PR base before mapping changed symbols and callers.</p>
        {commitSha !== result.base_sha ? <button disabled={busy || running} onClick={() => indexCommit(result.base_sha)}>Index PR base {result.base_sha.slice(0, 7)}</button>
          : <p>The base is now indexed. Analyze this PR again to update its report.</p>}</div>}
      <div className="analysis-stats"><span><strong>{result.changed_file_count}</strong> changed files</span>
        <span><strong>{result.comparable ? result.changed_symbol_count : "—"}</strong> changed definitions</span>
        <span><strong>{result.impact?.affected_file_count ?? "—"}</strong> potential dependent files</span></div>
      <div className="analysis-table-wrap"><table><caption>Changed files</caption><thead><tr><th>Path</th><th>Change</th><th>Lines</th><th>Mapping</th></tr></thead>
        <tbody>{result.files.map(file => <tr key={file.path}><td>{file.path}</td><td>{file.status}</td><td>+{file.additions} / −{file.deletions}</td>
          <td>{!file.supported ? "Unsupported language" : !file.indexed ? "Not in base index" : !result.comparable ? "Base required" : `${file.changed_symbol_ids.length} definitions${file.patch_available ? "" : " · patch missing"}`}</td></tr>)}</tbody></table></div>
      {result.impact && <><p className="intelligence-note">Potential impact: {result.impact.affected_symbol_count} possible callers · {result.impact.scope} scope.</p>
        <div className="analysis-list">{result.impact.files.map(file => <span key={file.file_id} className="pr-dependent">{file.path}{file.is_test ? " · test" : ""}</span>)}</div>
        {result.impact.truncated && <p className="notice">Impact traversal or display was capped.</p>}</>}
      <details><summary>Report limits</summary>{result.limitations.map(item => <p className="intelligence-note" key={item}>{item}</p>)}</details>
    </div>}
    {history.length > 0 && <details><summary>Saved PR reports</summary><div className="analysis-list">{history.map(item =>
      <button key={item.id} disabled={running} onClick={() => {setReport(item); setNumber(String(item.number));}}>#{item.number} · {item.status} · {new Date(item.created_at).toLocaleString()}</button>)}</div></details>}
  </details>;
}
