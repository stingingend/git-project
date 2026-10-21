"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileCode2,
  X,
} from "lucide-react";
import type { FileDetail, SourceSelection, SymbolRecord } from "../lib/types";
import { CallBrowser } from "./call-browser";
import {
  SOURCE_PAGE_SIZE as PAGE_SIZE,
  isSelectedLine,
  pageForLine,
} from "../lib/source-range";

export function SourceViewer({
  repositoryId,
  detail,
  busy,
  loadSymbols,
  selection,
  selectSymbol,
  clearSelection,
}: {
  repositoryId: number;
  detail: FileDetail;
  busy: boolean;
  loadSymbols: (offset: number) => void;
  selection: SourceSelection | null;
  selectSymbol: (symbol: SymbolRecord) => void;
  clearSelection: () => void;
}) {
  const [tab, setTab] = useState<"source" | "symbols" | "calls">("source");
  const [page, setPage] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (panel.current) panel.current.scrollTop = 0;
  }, [page, tab, detail.symbols.offset]);
  const selected =
    selection?.commit_sha === detail.commit_sha &&
    selection.symbol.file_id === detail.file.id
      ? selection
      : null;
  useEffect(() => {
    if (selected) {
      setTab("source");
      setPage(pageForLine(selected.symbol.start_line));
    }
  }, [selected, detail.file.id, detail.commit_sha]);
  useEffect(() => {
    if (!selected || tab !== "source" || !panel.current) return;
    const row = panel.current.querySelector<HTMLElement>(
      `[data-line="${selected.symbol.start_line}"]`,
    );
    if (row) {
      const top =
        panel.current.scrollTop +
        row.getBoundingClientRect().top -
        panel.current.getBoundingClientRect().top -
        panel.current.clientHeight / 3;
      panel.current.scrollTo({ top: Math.max(0, top), behavior: "instant" });
    }
  }, [selected, page, tab]);
  const lines = detail.source ? detail.source.split("\n") : [];
  if (lines.at(-1) === "") lines.pop();
  const pages = Math.max(1, Math.ceil(lines.length / PAGE_SIZE));
  const symbols = detail.symbols;
  return (
    <div className="source-viewer">
      <div className="source-heading">
        <span title={detail.file.path}>
          <FileCode2 size={15} />
          {detail.file.path}
        </span>
        <a
          href={
            selected
              ? `${detail.github_url}#L${selected.symbol.start_line}-L${selected.symbol.end_line}`
              : detail.github_url
          }
          target="_blank"
          rel="noreferrer"
          aria-label={
            selected ? "View selected symbol on GitHub" : "View file on GitHub"
          }
        >
          GitHub <ExternalLink size={12} />
        </a>
      </div>
      {selected && (
        <div className="selection-banner">
          <span>
            <strong>{selected.symbol.name}</strong> · lines{" "}
            {selected.symbol.start_line}–{selected.symbol.end_line}
          </span>
          <button aria-label="Clear source selection" onClick={clearSelection}>
            <X size={13} />
          </button>
        </div>
      )}
      <div className="viewer-tabs" role="tablist" aria-label="File content">
        <button
          role="tab"
          aria-selected={tab === "source"}
          onClick={() => setTab("source")}
        >
          Source
        </button>
        <button
          role="tab"
          aria-selected={tab === "symbols"}
          onClick={() => setTab("symbols")}
        >
          Symbols <span>{detail.parsing ? symbols.total : "—"}</span>
        </button>
        <button role="tab" aria-selected={tab === "calls"} onClick={() => setTab("calls")}>Calls</button>
        <span className="mono">{detail.commit_sha.slice(0, 7)}</span>
      </div>
      {!detail.parsing && (
        <div className="inline-notice">
          Source collected. Run indexing to extract symbols.
        </div>
      )}
      {detail.parsing?.has_parse_errors && (
        <div className="inline-notice">
          Syntax errors found. Recovered symbols may be incomplete.
        </div>
      )}
      {tab === "calls" ? <CallBrowser repositoryId={repositoryId} fileId={detail.file.id}
        commitSha={detail.commit_sha} githubUrl={detail.github_url} busy={busy} selectSymbol={selectSymbol} /> : tab === "source" ? (
        <>
          <div
            ref={panel}
            tabIndex={0}
            className="code-scroll"
            role="tabpanel"
            aria-label="Source code"
          >
            <pre>
              {lines.length ? (
                lines
                  .slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
                  .map((line, index) => (
                    <div
                      key={page * PAGE_SIZE + index}
                      data-line={page * PAGE_SIZE + index + 1}
                      className={
                        selected &&
                        isSelectedLine(
                          page * PAGE_SIZE + index + 1,
                          selected.symbol.start_line,
                          selected.symbol.end_line,
                        )
                          ? "selected-source-line"
                          : ""
                      }
                    >
                      <span className="line-number">
                        {page * PAGE_SIZE + index + 1}
                      </span>
                      <code>{line || " "}</code>
                    </div>
                  ))
              ) : (
                <span className="empty-code">This file is empty.</span>
              )}
            </pre>
          </div>
          <div className="viewer-footer">
            <span>
              Python · UTF-8 <span className="footer-separator">/</span>{" "}
              {lines.length.toLocaleString()} lines
            </span>
            <div>
              <button
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
                aria-label="Previous source page"
              >
                <ChevronLeft size={14} />
              </button>
              <span>
                {page + 1} / {pages}
              </span>
              <button
                disabled={page + 1 >= pages}
                onClick={() => setPage(page + 1)}
                aria-label="Next source page"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </>
      ) : (
        <>
          <div
            ref={panel}
            tabIndex={0}
            className="symbol-list"
            role="tabpanel"
            aria-label="File symbols"
          >
            {symbols.items.map((symbol) => (
              <button
                className="symbol-row"
                key={symbol.id}
                disabled={busy}
                onClick={() => selectSymbol(symbol)}
              >
                <span className={`symbol-kind ${symbol.symbol_type}`}>
                  {symbol.symbol_type}
                </span>
                <span>
                  <strong>{symbol.name}</strong>
                  <code>{symbol.signature}</code>
                </span>
                <small>
                  L{symbol.start_line}–{symbol.end_line}
                  <ChevronRight size={11} />
                </small>
              </button>
            ))}
            {!symbols.items.length && (
              <div className="panel-empty">
                {detail.parsing
                  ? "No symbols on this page."
                  : "This file has not been parsed yet."}
              </div>
            )}
          </div>
          <div className="viewer-footer">
            <span>
              {symbols.total === null
                ? "Not parsed"
                : `${symbols.total.toLocaleString()} symbols`}{" "}
              · Select to view source
            </span>
            <div>
              <button
                aria-label="Previous symbol page"
                disabled={busy || symbols.offset === 0}
                onClick={() =>
                  loadSymbols(Math.max(0, symbols.offset - symbols.limit))
                }
              >
                <ChevronLeft size={14} />
              </button>
              <span>
                {symbols.items.length
                  ? `${symbols.offset + 1}–${symbols.offset + symbols.items.length}`
                  : "0"}
              </span>
              <button
                aria-label="Next symbol page"
                disabled={
                  busy || symbols.offset + symbols.limit >= (symbols.total ?? 0)
                }
                onClick={() => loadSymbols(symbols.offset + symbols.limit)}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
