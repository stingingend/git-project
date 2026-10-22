"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Search,
  X,
} from "lucide-react";
import { createApi } from "../lib/api";
import type { SearchHit, SearchPage } from "../lib/types";

const api = createApi();

export function SymbolSearch({
  repositoryId,
  parsed,
  disabled,
  select,
}: {
  repositoryId: number;
  parsed: boolean;
  disabled: boolean;
  select: (hit: SearchHit, commitSha: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);
  const [results, setResults] = useState<SearchPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setResults(null);
    setError("");
    if (!query.trim() || !parsed || disabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .search(repositoryId, query.trim(), kind, offset)
        .then((page) => {
          if (active) setResults(page);
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, kind, offset, repositoryId, parsed, disabled]);

  return (
    <section className="symbol-search" aria-label="Repository symbol search">
      <div className="search-heading">
        <h2>
          <Search size={15} />
          Find a definition
        </h2>
        <span>Across the indexed repository</span>
      </div>
      <div className="search-controls">
        <div className="search-field">
          <Search size={15} />
          <input
            aria-label="Search symbols"
            placeholder={
              parsed
                ? "Search names, signatures, or file paths…"
                : "Run indexing to enable symbol search"
            }
            maxLength={200}
            value={query}
            disabled={!parsed || disabled}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          {query && (
            <button
              disabled={disabled}
              aria-label="Clear symbol search"
              onClick={() => {
                setQuery("");
                setOffset(0);
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
        <select
          aria-label="Filter symbol type"
          value={kind}
          disabled={!parsed || disabled}
          onChange={(event) => {
            setKind(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All symbol types</option>
          {["function", "class", "method", "import", "interface", "type"].map(
            (type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ),
          )}
        </select>
      </div>
      <div className="search-status" aria-live="polite">
        {loading ? (
          <>
            <LoaderCircle size={12} className="spin" />
            Searching the saved index…
          </>
        ) : error ? (
          <span role="alert">{error}</span>
        ) : results ? (
          !results.parsed ? (
            "The parsed index is no longer available. Refresh and run indexing again."
          ) : (
            `${results.total.toLocaleString()} ${results.total === 1 ? "match" : "matches"} for “${results.query}”`
          )
        ) : (
          "Find a symbol, then select it to jump to its source."
        )}
      </div>
      {!!results?.items.length && (
        <>
          <div className="search-results">
            {results.items.map((hit) => (
              <button
                className="search-result"
                key={hit.symbol.id}
                disabled={disabled}
                onClick={() =>
                  results.commit_sha && select(hit, results.commit_sha)
                }
              >
                <span className={`symbol-kind ${hit.symbol.symbol_type}`}>
                  {hit.symbol.symbol_type}
                </span>
                <span className="search-result-copy">
                  <strong>{hit.symbol.name}</strong>
                  {hit.symbol.signature !== hit.symbol.name && (
                    <code title={hit.symbol.signature}>
                      {hit.symbol.signature}
                    </code>
                  )}
                  <small>
                    {hit.path} · L{hit.symbol.start_line}–{hit.symbol.end_line}
                    {hit.has_parse_errors && " · Syntax errors"}
                  </small>
                </span>
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
          <div className="search-pagination">
            <span>
              {offset + 1}–{offset + results.items.length} of{" "}
              {results.total.toLocaleString()} ·{" "}
              {results.commit_sha?.slice(0, 7)}
            </span>
            <div>
              <button
                aria-label="Previous search results"
                disabled={disabled || loading || offset === 0}
                onClick={() => setOffset(Math.max(0, offset - results.limit))}
              >
                <ChevronLeft size={14} />
              </button>
              <button
                aria-label="Next search results"
                disabled={
                  disabled || loading || offset + results.limit >= results.total
                }
                onClick={() => setOffset(offset + results.limit)}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
