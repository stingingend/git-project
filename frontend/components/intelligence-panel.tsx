"use client";
import { useEffect, useState } from "react";
import { BrainCircuit, ExternalLink, LoaderCircle, Search } from "lucide-react";
import { createApi } from "../lib/api";
import type { CitedAnswer, SemanticHit, SemanticResults } from "../lib/types";

const api = createApi();

export function IntelligencePanel({ repositoryId, commitSha, parsed, busy, select }: {
  repositoryId: number; commitSha: string; parsed: boolean; busy: boolean;
  select: (hit: SemanticHit, commit: string) => void;
}) {
  const [ready, setReady] = useState(false);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SemanticResults | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"search" | "question">("search");
  const [generated, setGenerated] = useState(false);
  const [answer, setAnswer] = useState<CitedAnswer | null>(null);
  useEffect(() => {
    let current = true;
    if (parsed) api.semanticStatus(repositoryId).then(status => { if (current) setReady(status.ready); })
      .catch(reason => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [repositoryId, commitSha, parsed]);
  async function build() {
    setWorking(true); setError("");
    try {
      const indexed = await api.buildSemantic(repositoryId);
      setReady(true); setNote(`${indexed.embedded} units embedded · ${indexed.reused} embeddings reused`);
    } catch (reason) { setError((reason as Error).message); }
    finally { setWorking(false); }
  }
  async function search(event: React.FormEvent) {
    event.preventDefault(); setWorking(true); setError(""); setResult(null); setAnswer(null);
    try {
      if (mode === "question") {
        const found = await api.ask(repositoryId, query.trim(), generated);
        if (found.commit_sha !== commitSha) throw new Error("The index changed. Refresh this repository.");
        setAnswer(found);
      } else {
        const found = await api.semanticSearch(repositoryId, query.trim());
        if (found.commit_sha !== commitSha) throw new Error("The index changed. Refresh this repository.");
        setResult(found);
      }
    } catch (reason) { setError((reason as Error).message); }
    finally { setWorking(false); }
  }
  return <section className="intelligence-panel" aria-label="Repository intelligence">
    <div className="intelligence-heading"><div><h2><BrainCircuit size={19} /> Explore by meaning</h2>
      <p>Find functions, classes, and modules using natural language.</p></div>
      <button className="secondary" onClick={() => void build()} disabled={busy || working || !parsed}>
        {working ? <LoaderCircle size={14} className="spin" /> : <BrainCircuit size={14} />}
        {ready ? "Update semantic index" : "Build semantic index"}</button></div>
    <p className="intelligence-note">Embeddings run locally. The first build downloads a pinned model; your source stays on this machine.</p>
    <div className="intelligence-tabs" role="group" aria-label="Intelligence mode">
      <button aria-pressed={mode === "search"} onClick={() => setMode("search")} disabled={working}>Semantic search</button>
      <button aria-pressed={mode === "question"} onClick={() => setMode("question")} disabled={working}>Ask repository</button>
    </div>
    {!parsed && <p>Index this repository to enable semantic search.</p>}
    {note && <p role="status">{note}</p>}
    <form className="intelligence-query" onSubmit={search}>
      <input aria-label={mode === "search" ? "Semantic search query" : "Repository question"}
        placeholder={mode === "search" ? "e.g. validate authentication tokens" : "Where are signed tokens validated?"} value={query}
        maxLength={mode === "search" ? 500 : 1000} onChange={event => setQuery(event.target.value)} disabled={busy || working || !ready} />
      <button className="primary" disabled={busy || working || !ready || query.trim().length < 2}><Search size={15} />
        {mode === "search" ? "Search by meaning" : "Find cited answers"}</button>
    </form>
    {mode === "question" && <label className="intelligence-note"><input type="checkbox" checked={generated}
      onChange={event => setGenerated(event.target.checked)} /> Use the configured model server for an explanation</label>}
    {error && <p role="alert" className="intelligence-error">{error}</p>}
    {mode === "search" && result && <div className="intelligence-results" aria-live="polite">
      <p>{result.items.length} matches · commit {result.commit_sha.slice(0, 7)} · cosine similarity</p>
      {result.items.length === 0 && <p>No sufficiently similar source found. Try more specific words.</p>}
      {result.items.map(hit => <article key={hit.document_id}>
        <div><button disabled={busy} onClick={() => select(hit, result.commit_sha)}>{hit.title}</button><span>{hit.score.toFixed(3)}</span></div>
        <small>{hit.path} · L{hit.start_line}–{hit.end_line}{hit.truncated ? " · embedding excerpt capped" : ""}</small>
        <pre>{hit.excerpt}</pre><a href={hit.github_url} target="_blank" rel="noreferrer">View pinned source <ExternalLink size={12} /></a>
      </article>)}
    </div>}
    {mode === "question" && answer && <div className="intelligence-results" aria-live="polite">
      <p>{answer.mode === "generated" ? "Generated explanation" : "Source-backed findings"} · commit {answer.commit_sha.slice(0, 7)}</p>
      {answer.notice && <p>{answer.notice}</p>}
      <p className="cited-answer">{answer.answer}</p>
      {answer.citations.map(citation => <article key={citation.id}>
        <strong>[{citation.id}] {citation.title}</strong><p>{citation.path} · L{citation.start_line}–{citation.end_line}</p>
        <pre>{citation.quote}{citation.quote_truncated ? "\n…" : ""}</pre>
        <a href={citation.github_url} target="_blank" rel="noreferrer">View pinned evidence <ExternalLink size={12} /></a>
      </article>)}
    </div>}
  </section>;
}
