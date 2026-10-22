"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Box,
  Braces,
  Check,
  ChevronRight,
  CircleDot,
  Code2,
  ExternalLink,
  FileCode2,
  Files,
  GitBranch,
  Github,
  Layers3,
  LoaderCircle,
  Map,
  Plus,
  RefreshCw,
  Search,
  Terminal,
  X,
} from "lucide-react";
import { IndexChangesView } from "../../components/index-changes";
import {
  ApiError,
  activeJob,
  createApi,
  startIndexJob,
  loadSymbolSource,
} from "../../lib/api";
import type {
  FileDetail,
  Overview,
  Repository,
  SourceFile,
  Stage,
  SearchHit,
  SourceSelection,
  IndexJob,
} from "../../lib/types";
import { SourceViewer } from "../../components/source-viewer";
import { SymbolSearch } from "../../components/symbol-search";
import { Relationships } from "../../components/relationships";
import { DependencyGraph } from "../../components/dependency-graph";
import { IntelligencePanel } from "../../components/intelligence-panel";
import { AnalysisPanel } from "../../components/analysis-panel";
import { PullRequestPanel } from "../../components/pull-request-panel";

const api = createApi();
const stages: Stage[] = ["registering", "queued", "ingesting", "parsing"];
const stageLabels = [
  "Connect repository",
  "Schedule job",
  "Collect Python source",
  "Extract symbols",
];
const number = (value: number | undefined) =>
  value === undefined ? "—" : value.toLocaleString();

export default function Home() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [detail, setDetail] = useState<FileDetail | null>(null);
  const [activeFile, setActiveFile] = useState<number | null>(null);
  const [selection, setSelection] = useState<SourceSelection | null>(null);
  const [url, setUrl] = useState("");
  const [filter, setFilter] = useState("");
  const [visibleFiles, setVisibleFiles] = useState(100);
  const [initialLoading, setInitialLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<Stage | "complete" | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [job, setJob] = useState<IndexJob | null>(null);
  const [jobHistory, setJobHistory] = useState<IndexJob[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const fileRequest = useRef(0);
  const explorer = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selection)
      explorer.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  }, [selection]);

  useEffect(() => {
    let active = true;
    Promise.all([api.repositories(), api.jobs()])
      .then(([data, history]) => {
        if (!active) return;
        setRepositories(data);
        setJobHistory(history);
        const latest = history[0];
        setJob(latest ?? null);
        setBusy(latest ? activeJob(latest) : false);
        setSelectedId(latest?.repository_id ?? data.at(-1)?.id ?? null);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setInitialLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!job) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let disconnected = false;
    const id = job.id;
    async function poll() {
      try {
        const current = await api.job(id);
        if (!active) return;
        if (disconnected) {
          setError("");
          disconnected = false;
        }
        setJob(current);
        setJobHistory((history) =>
          [current, ...history.filter((item) => item.id !== current.id)]
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .slice(0, 10),
        );
        const running = activeJob(current);
        if (running) setBusy(true);
        setStage(
          current.status === "succeeded"
            ? "complete"
            : running
              ? current.stage === "complete"
                ? "parsing"
                : current.stage
              : null,
        );
        if (!running) {
          if (current.error) setError(current.error);
          await refresh(current.repository_id, () => active);
          if (active) setBusy(false);
          return;
        }
      } catch (reason) {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setError(
            "This indexing job no longer exists. Refresh the workspace.",
          );
          setBusy(false);
          setStage(null);
          return;
        }
        disconnected = true;
        setError(
          `Cannot check indexing status. The job may still be running. Reconnecting… ${(reason as Error).message}`,
        );
      }
      if (active) timer = setTimeout(poll, disconnected ? 2000 : 1000);
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job?.id]);

  useEffect(() => {
    let active = true;
    fileRequest.current++;
    setOverview(null);
    setFiles([]);
    setDetail(null);
    setSelection(null);
    setActiveFile(null);
    setFilter("");
    setVisibleFiles(100);
    setFileLoading(false);
    if (selectedId === null) return;
    setOverviewLoading(true);
    Promise.all([api.overview(selectedId), api.files(selectedId)])
      .then(([data, sourceFiles]) => {
        if (active) {
          setOverview(data);
          setFiles(sourceFiles);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setOverviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId, revision]);

  async function refresh(preferredId?: number, stillCurrent = () => true) {
    const data = await api.repositories();
    if (!stillCurrent()) return;
    setRepositories(data);
    setSelectedId(
      (current) =>
        preferredId ??
        (data.some((repo) => repo.id === current)
          ? current
          : (data.at(-1)?.id ?? null)),
    );
    setRevision((current) => current + 1);
  }

  async function retryConnection() {
    setError("");
    setInitialLoading(true);
    try {
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setInitialLoading(false);
    }
  }

  async function runIndex(repositoryUrl: string) {
    setBusy(true);
    setError("");
    setStage("registering");
    setJob(null);
    setSelection(null);
    fileRequest.current++;
    setFileLoading(false);
    let targetId: number | undefined;
    let failure = "";
    let accepted = false;
    try {
      const started = await startIndexJob(repositoryUrl, api);
      targetId = started.repository.id;
      setJob(started.job);
      accepted = true;
      setStage(
        started.job.stage === "complete" ? "complete" : started.job.stage,
      );
      setUrl("");
    } catch (e) {
      failure = (e as Error).message;
      setStage(null);
    }
    try {
      await refresh(targetId);
    } catch (e) {
      if (!failure) failure = (e as Error).message;
    }
    if (failure) setError(failure);
    if (failure && !accepted) setBusy(false);
  }

  async function indexCommit(commitSha: string) {
    if (selectedId === null || busy) return;
    setBusy(true);
    setError("");
    setStage("queued");
    setSelection(null);
    fileRequest.current++;
    setFileLoading(false);
    try {
      const started = await api.startJob(selectedId, commitSha);
      setJob(started);
      setStage(started.stage === "complete" ? "complete" : started.stage);
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
      setStage(null);
    }
  }

  async function openFile(
    fileId: number,
    offset = 0,
    preserveSelection = false,
  ) {
    if (selectedId === null || busy) return;
    const request = ++fileRequest.current;
    if (!preserveSelection) setSelection(null);
    setActiveFile(fileId);
    setFileLoading(true);
    // Keep the current source and graph mounted while the next file loads.
    try {
      const data = await api.file(selectedId, fileId, offset);
      if (request === fileRequest.current) setDetail(data);
    } catch (e) {
      if (request === fileRequest.current) setError((e as Error).message);
    } finally {
      if (request === fileRequest.current) setFileLoading(false);
    }
  }

  function focusConnect() {
    input.current?.scrollIntoView({
      block: "center",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    input.current?.focus({ preventScroll: true });
  }

  async function openSymbol(hit: SearchHit, commitSha: string) {
    if (selectedId === null || busy) return;
    const request = ++fileRequest.current;
    setFileLoading(true);
    setSelection(null);
    setError("");
    setActiveFile(hit.symbol.file_id);
    if (hit.symbol.file_id !== activeFile) setDetail(null);
    try {
      const loaded = await loadSymbolSource(api, selectedId, hit, commitSha);
      if (request !== fileRequest.current) return;
      setDetail(loaded.detail);
      setSelection({
        symbol: loaded.symbol,
        commit_sha: loaded.commit_sha,
        request,
      });
      setFilter("");
    } catch (e) {
      if (request === fileRequest.current) setError((e as Error).message);
    } finally {
      if (request === fileRequest.current) setFileLoading(false);
    }
  }

  const filtered = files.filter((file) =>
    file.path.toLowerCase().includes(filter.toLowerCase()),
  );
  const step =
    stage === "complete" ? stages.length : stage ? stages.indexOf(stage) : -1;
  const jobRepository = repositories.find(
    (repo) => repo.id === job?.repository_id,
  );

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-mark">
            <Map size={22} />
          </span>
          CodeAtlas
        </a>
        <div className="sidebar-section">
          WORKSPACE <span>PERSONAL</span>
        </div>
        <div className="workspace-name">
          <span className="workspace-avatar">
            <Terminal size={17} />
          </span>
          <div>
            Personal workspace<small>Repository intelligence</small>
          </div>
        </div>
        <div className="nav-active">
          <Layers3 size={16} />
          Repository explorer<span>{repositories.length}</span>
        </div>
        <div className="sidebar-section repo-label">
          REPOSITORIES
          <button
            aria-label="Connect a repository"
            disabled={busy}
            onClick={focusConnect}
          >
            <Plus size={15} />
          </button>
        </div>
        <nav aria-label="Repositories" className="repo-nav">
          {repositories.map((repo) => (
            <button
              key={repo.id}
              disabled={busy}
              className={
                selectedId === repo.id ? "repo-link selected" : "repo-link"
              }
              onClick={() => {
                setSelectedId(repo.id);
                setStage(null);
                setError("");
              }}
            >
              <span className={`status-dot ${repo.status}`} />
              <span>
                {repo.name}
                <small>{repo.owner}</small>
              </span>
            </button>
          ))}
          {!repositories.length && (
            <p>
              Your connected repositories
              <br />
              will appear here.
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <span className="engine-icon">
            <Braces size={17} />
          </span>
          <div>
            Powered by structure<small>Python · Tree-sitter</small>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            Workspace
            <ChevronRight size={13} />
            <strong>Repositories</strong>
          </div>
          <span>
            <span className="status-dot" />
            Repository intelligence
          </span>
        </header>
        <div className="content">
          <section className="page-heading">
            <div>
              <div className="eyebrow">YOUR CODE, IN CONTEXT</div>
              <h1>Understand what you build.</h1>
              <p>
                A clear view of the files and symbols behind your repository.
              </p>
            </div>
            <div className="heading-mark" aria-hidden="true">
              <Code2 size={31} />
            </div>
          </section>
          <section className="connect-card" aria-labelledby="connect-title">
            <div className="connect-intro">
              <Github size={20} />
              <div>
                <h2 id="connect-title">Bring your repository into focus</h2>
                <p>
                  Connect a public GitHub repository to explore its Python
                  source.
                </p>
              </div>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void runIndex(url);
              }}
            >
              <label htmlFor="github-url" className="sr-only">
                GitHub repository URL
              </label>
              <div className="url-input">
                <Github size={16} />
                <input
                  ref={input}
                  id="github-url"
                  required
                  type="url"
                  placeholder="https://github.com/owner/repository"
                  value={url}
                  disabled={busy}
                  onChange={(event) => setUrl(event.target.value)}
                />
              </div>
              <button className="primary" type="submit" disabled={busy}>
                {busy ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Plus size={15} />
                )}{" "}
                {busy ? "Indexing repository…" : "Index repository"}
                {!busy && <ArrowRight size={15} />}
              </button>
            </form>
            <div className="connect-foot">
              <span>
                <CircleDot size={11} />
                Public repos · Python source · No API keys
              </span>
              <button
                disabled={busy}
                onClick={() => {
                  setUrl("https://github.com/pallets/itsdangerous");
                  input.current?.focus();
                }}
              >
                Try itsdangerous <ArrowRight size={11} />
              </button>
            </div>
          </section>

          {stage && (
            <section
              className={`job-panel ${stage === "complete" ? "job-complete" : ""}`}
              aria-live="polite"
            >
              <div className="job-title">
                {busy ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Check size={15} />
                )}
                <strong>
                  {stage === "complete"
                    ? "Repository indexed"
                    : stage === "registering"
                      ? "Connecting your repository"
                      : stage === "queued"
                        ? "Indexing job scheduled"
                        : stage === "ingesting"
                          ? "Collecting Python source"
                          : "Extracting symbols"}
                </strong>
                <span>
                  {stage === "complete"
                    ? "Ready to explore"
                    : "Runs on the API. You can reload this page."}
                </span>
              </div>
              <p className="job-reference">
                {job
                  ? `Job ${job.id.slice(0, 8)} · ${jobRepository ? `${jobRepository.owner}/${jobRepository.name}` : `Repository ${job.repository_id}`} · Progress saved`
                  : "Creating a background indexing job…"}
              </p>
              {job?.changes && <IndexChangesView changes={job.changes} />}
              <ol className="job-steps">
                {stageLabels.map((label, index) => (
                  <li
                    key={label}
                    className={
                      index < step ? "done" : index === step ? "current" : ""
                    }
                  >
                    <span>
                      {index < step ? <Check size={11} /> : index + 1}
                    </span>
                    {label}
                    {index < stages.length - 1 && <div />}
                  </li>
                ))}
              </ol>
            </section>
          )}
          {jobHistory.length > 0 && (
            <details className="job-history">
              <summary>
                Recent indexing runs <span>{jobHistory.length}</span>
              </summary>
              {jobHistory.map((item) => (
                <article key={item.id}>
                  <div>
                    <strong>
                      {repositories.find(
                        (repo) => repo.id === item.repository_id,
                      )?.name ?? `Repository ${item.repository_id}`}
                    </strong>
                    <span className={`job-state ${item.status}`}>
                      {item.status}
                    </span>
                  </div>
                  <small>
                    {item.id.slice(0, 8)} · {item.stage} ·{" "}
                    {new Date(item.created_at).toLocaleString()}
                    {item.commit_sha ? ` · ${item.commit_sha.slice(0, 7)}` : ""}
                  </small>
                  {item.changes && <IndexChangesView changes={item.changes} />}
                  {item.error && <p>{item.error}</p>}
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      setJob(item);
                      setSelectedId(item.repository_id);
                    }}
                  >
                    View repository
                  </button>
                </article>
              ))}
            </details>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={15} />
              </button>
            </div>
          )}

          {initialLoading || overviewLoading ? (
            <div className="loading-state">
              <LoaderCircle size={23} className="spin" />
              <p>
                {initialLoading
                  ? "Connecting to your workspace…"
                  : "Loading repository index…"}
              </p>
            </div>
          ) : overview ? (
            <>
              <section className="repository-heading">
                <div>
                  <div className="repo-heading-title">
                    <Github size={21} />
                    <h2>
                      <span>{overview.repository.owner} / </span>
                      {overview.repository.name}
                    </h2>
                    <span
                      className={`state-pill ${overview.repository.status}`}
                    >
                      {overview.repository.status}
                    </span>
                  </div>
                  <div className="repo-metadata">
                    {overview.snapshot ? (
                      <>
                        <span>
                          <GitBranch size={12} />
                          {overview.snapshot.default_branch}
                        </span>
                        <span className="mono">
                          {overview.snapshot.commit_sha.slice(0, 7)}
                        </span>
                        <span>
                          Collected{" "}
                          {new Date(
                            overview.snapshot.ingested_at,
                          ).toLocaleDateString()}
                        </span>
                      </>
                    ) : (
                      <span>
                        Registered · Source has not been collected yet
                      </span>
                    )}
                  </div>
                </div>
                <div className="repo-actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void runIndex(overview.repository.github_url)
                    }
                  >
                    <RefreshCw size={13} />
                    {overview.parsing ? "Re-index" : "Run indexing"}
                  </button>
                  <a
                    className="icon-button"
                    aria-label="Open repository on GitHub"
                    href={overview.repository.github_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={15} />
                  </a>
                </div>
              </section>
              <div className="statistics">
                {[
                  {
                    label: "Python files",
                    value: overview.snapshot?.file_count,
                    caption: overview.snapshot
                      ? `${number(overview.snapshot.line_count)} lines of source`
                      : "Awaiting ingestion",
                    icon: Files,
                  },
                  {
                    label: "Functions & methods",
                    value: overview.parsing
                      ? overview.parsing.functions + overview.parsing.methods
                      : undefined,
                    caption: overview.parsing
                      ? "Named definitions"
                      : "Awaiting parsing",
                    icon: Braces,
                  },
                  {
                    label: "Classes",
                    value: overview.parsing?.classes,
                    caption: overview.parsing
                      ? "Extracted from syntax trees"
                      : "Awaiting parsing",
                    icon: Box,
                  },
                  {
                    label: "Import statements",
                    value: overview.parsing?.imports,
                    caption: overview.parsing
                      ? `${number(overview.parsing.symbol_count)} total symbols`
                      : "Awaiting parsing",
                    icon: GitBranch,
                  },
                ].map(({ label, value, caption, icon: Icon }) => (
                  <article key={label}>
                    <div>
                      {label}
                      <Icon size={16} />
                    </div>
                    <strong>{number(value)}</strong>
                    <small>{caption}</small>
                  </article>
                ))}
              </div>
              {!!overview.snapshot?.skipped_files && (
                <div className="notice">
                  {overview.snapshot.skipped_files} Python files skipped because
                  of exclusions, symlinks, size limits, or unsupported encoding.
                </div>
              )}
              {!!overview.parsing?.parse_error_files && (
                <div className="notice">
                  {overview.parsing.parse_error_files} files have syntax errors.
                  Recovered symbols may be incomplete.
                </div>
              )}
              <IntelligencePanel
                key={`intelligence:${selectedId}:${revision}`}
                repositoryId={overview.repository.id}
                commitSha={overview.snapshot?.commit_sha ?? ""}
                parsed={overview.parsing !== null}
                busy={busy}
                select={(hit, commit) => {
                  if (hit.symbol)
                    void openSymbol(
                      {
                        symbol: hit.symbol,
                        path: hit.path,
                        has_parse_errors: false,
                      },
                      commit,
                    );
                  else if (commit === overview.snapshot?.commit_sha)
                    void openFile(hit.file_id);
                }}
              />
              {overview.parsing && (
                <AnalysisPanel
                  key={`analysis:${selectedId}:${revision}`}
                  repositoryId={overview.repository.id}
                  commitSha={overview.snapshot?.commit_sha ?? ""}
                  files={files}
                  busy={busy}
                  selectedSymbol={selection?.symbol}
                  selectFile={(fileId) => void openFile(fileId)}
                  selectSymbol={(hit, commit) => void openSymbol(hit, commit)}
                />
              )}
              <PullRequestPanel
                key={`pr:${selectedId}:${revision}`}
                repositoryId={overview.repository.id}
                commitSha={overview.snapshot?.commit_sha ?? ""}
                busy={busy}
                indexCommit={(sha) => void indexCommit(sha)}
              />
              <SymbolSearch
                key={`${selectedId}:${revision}`}
                repositoryId={overview.repository.id}
                parsed={overview.parsing !== null}
                disabled={busy}
                select={(hit, commit) => void openSymbol(hit, commit)}
              />
              <div className="section-heading">
                <h2>
                  Repository explorer <span>{files.length}</span>
                </h2>
                <span>
                  <span className="status-dot parsed" />
                  Saved source snapshot
                </span>
              </div>
              <section className="explorer" ref={explorer}>
                <div className="file-browser">
                  <div className="filter-input">
                    <Search size={14} />
                    <input
                      aria-label="Filter files"
                      placeholder="Filter files…"
                      value={filter}
                      onChange={(event) => {
                        setFilter(event.target.value);
                        setVisibleFiles(100);
                      }}
                    />
                  </div>
                  <div className="tree-label">PYTHON SOURCE</div>
                  <div className="file-list">
                    {filtered.slice(0, visibleFiles).map((file) => (
                      <button
                        title={file.path}
                        disabled={busy}
                        key={file.id}
                        onClick={() => void openFile(file.id)}
                        className={
                          activeFile === file.id
                            ? "file-row active-file"
                            : "file-row"
                        }
                      >
                        <FileCode2 size={14} />
                        <span>{file.path}</span>
                        <small>{file.line_count}</small>
                      </button>
                    ))}
                    {filtered.length > visibleFiles && (
                      <button
                        className="show-more"
                        onClick={() => setVisibleFiles((count) => count + 100)}
                      >
                        Show more files ({filtered.length - visibleFiles}{" "}
                        remaining)
                      </button>
                    )}
                    {!filtered.length && (
                      <p className="file-empty">
                        {filter
                          ? "No matching files."
                          : overview.snapshot
                            ? "No supported Python files in this snapshot."
                            : "Run indexing to collect source files."}
                      </p>
                    )}
                  </div>
                </div>
                <div className="file-content">
                  {detail ? (
                    <>
                      <SourceViewer
                        repositoryId={selectedId!}
                        key={`${detail.file.id}:${detail.commit_sha}`}
                        detail={detail}
                        busy={fileLoading || busy}
                        selection={selection}
                        clearSelection={() => setSelection(null)}
                        selectSymbol={(symbol) =>
                          void openSymbol(
                            {
                              symbol,
                              path:
                                files.find((file) => file.id === symbol.file_id)
                                  ?.path ?? detail.file.path,
                              has_parse_errors:
                                detail.parsing?.has_parse_errors ?? false,
                            },
                            detail.commit_sha,
                          )
                        }
                        loadSymbols={(offset) =>
                          void openFile(detail.file.id, offset, true)
                        }
                      />
                      {fileLoading && (
                        <div className="file-refresh" role="status">
                          <LoaderCircle size={12} className="spin" />
                          Loading source…
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="source-placeholder">
                      {fileLoading ? (
                        <>
                          <LoaderCircle className="spin" size={25} />
                          <h3>Loading source…</h3>
                        </>
                      ) : (
                        <>
                          <span className="placeholder-icon">
                            <Code2 size={29} />
                          </span>
                          <h3>Get to know the code.</h3>
                          <p>
                            Select a file to explore its saved source and
                            symbols.
                          </p>
                          <small>
                            <CircleDot size={11} />
                            Source tied to a specific Git commit
                          </small>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </section>
              {detail && (
                <DependencyGraph
                  key={`graph:${selectedId}:${revision}:${detail.commit_sha}`}
                  repositoryId={selectedId!}
                  fileId={detail.file.id}
                  filePath={detail.file.path}
                  commitSha={detail.commit_sha}
                  busy={fileLoading || busy}
                  openFile={(id) => void openFile(id)}
                />
              )}
              {detail && (
                <Relationships
                  key={`relations:${selectedId}:${revision}:${detail.file.id}:${detail.commit_sha}`}
                  repositoryId={selectedId!}
                  fileId={detail.file.id}
                  filePath={detail.file.path}
                  commitSha={detail.commit_sha}
                  busy={fileLoading || busy}
                  openFile={(id) => void openFile(id)}
                />
              )}
            </>
          ) : selectedId !== null ? (
            <div className="empty-workspace">
              <h2>We couldn’t load this repository.</h2>
              <p>Check that the API is running, then try again.</p>
              <button
                className="secondary"
                onClick={() => void retryConnection()}
              >
                <RefreshCw size={14} />
                Retry connection
              </button>
            </div>
          ) : (
            <section className="empty-workspace">
              <div className="empty-graphic" aria-hidden="true">
                <span>
                  <Github size={23} />
                </span>
                <i />
                <span>
                  <FileCode2 size={21} />
                </span>
                <i />
                <span>
                  <Braces size={23} />
                </span>
              </div>
              <div className="eyebrow">FROM REPOSITORY TO UNDERSTANDING</div>
              <h2>
                Every codebase has a structure.
                <br />
                <span>Let’s make yours visible.</span>
              </h2>
              <p>
                Index a repository to discover its Python files, inspect real
                definitions,
                <br className="desktop-break" /> and read the source behind
                them.
              </p>
              <div className="empty-features">
                <span>
                  <Files size={13} />
                  Source discovery
                </span>
                <span>
                  <Braces size={13} />
                  Syntax-aware symbols
                </span>
                <span>
                  <GitBranch size={13} />
                  Commit-pinned source
                </span>
              </div>
              {error && (
                <button
                  className="secondary retry-empty"
                  onClick={() => void retryConnection()}
                >
                  <RefreshCw size={14} />
                  Retry API connection
                </button>
              )}
            </section>
          )}
          <div className="mobile-repository-picker">
            <label htmlFor="repository-choice">Repository</label>
            <select
              id="repository-choice"
              value={selectedId ?? ""}
              disabled={busy || !repositories.length}
              onChange={(event) => setSelectedId(Number(event.target.value))}
            >
              {!repositories.length && (
                <option value="">No repositories yet</option>
              )}
              {repositories.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.owner}/{repo.name}
                </option>
              ))}
            </select>
          </div>
          <footer className="page-footer">
            <span>
              <Map size={13} />
              CodeAtlas <i /> Understand what you build.
            </span>
            <span>Structural intelligence. No LLM required.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
