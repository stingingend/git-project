"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileCode2,
} from "lucide-react";
import type { FileDetail } from "../lib/types";

const PAGE_SIZE = 200;

export function SourceViewer({
  detail,
  busy,
  loadSymbols,
}: {
  detail: FileDetail;
  busy: boolean;
  loadSymbols: (offset: number) => void;
}) {
  const [tab, setTab] = useState<"source" | "symbols">("source");
  const [page, setPage] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (panel.current) panel.current.scrollTop = 0;
  }, [page, tab, detail.symbols.offset]);
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
          href={detail.github_url}
          target="_blank"
          rel="noreferrer"
          aria-label="View file on GitHub"
        >
          GitHub <ExternalLink size={12} />
        </a>
      </div>
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
      {tab === "source" ? (
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
                    <div key={page * PAGE_SIZE + index}>
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
              <a
                className="symbol-row"
                key={symbol.id}
                href={`${detail.github_url}#L${symbol.start_line}-L${symbol.end_line}`}
                target="_blank"
                rel="noreferrer"
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
                  <ExternalLink size={11} />
                </small>
              </a>
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
              · Links open the indexed commit
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
