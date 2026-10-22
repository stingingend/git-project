export type Repository = {
  id: number;
  owner: string;
  name: string;
  github_url: string;
  status: "registered" | "ingested" | "parsed";
  created_at: string;
};
export type Overview = {
  repository: Repository;
  snapshot: null | {
    commit_sha: string;
    default_branch: string;
    file_count: number;
    line_count: number;
    skipped_files: number;
    ingested_at: string;
  };
  parsing: null | {
    symbol_count: number;
    functions: number;
    methods: number;
    classes: number;
    imports: number;
    parse_error_files: number;
    parsed_at: string;
  };
};
export type SourceFile = {
  id: number;
  path: string;
  language: string;
  line_count: number;
  content_hash: string;
};
export type SymbolRecord = {
  id: number;
  file_id: number;
  name: string;
  qualified_name: string;
  signature: string;
  symbol_type: string;
  start_line: number;
  end_line: number;
};
export type FileDetail = {
  file: SourceFile;
  source: string;
  commit_sha: string;
  github_url: string;
  parsing: null | { has_parse_errors: boolean; symbol_count: number };
  symbols: {
    items: SymbolRecord[];
    total: number | null;
    limit: number;
    offset: number;
  };
};
export type Stage = "registering" | "queued" | "ingesting" | "parsing";

export type IndexChanges = {
  added: number;
  changed: number;
  removed: number;
  unchanged: number;
  parsed_files: number | null;
  reused_files: number | null;
};

export type IndexJob = {
  id: string;
  repository_id: number;
  status: "queued" | "running" | "succeeded" | "failed" | "interrupted";
  stage: "queued" | "ingesting" | "parsing" | "complete";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  commit_sha: string | null;
  changes?: IndexChanges | null;
};

export type SearchHit = {
  symbol: SymbolRecord;
  path: string;
  has_parse_errors: boolean;
};

export type SemanticHit = {
  document_id: number; score: number; path: string; file_id: number;
  symbol: SymbolRecord | null; title: string; start_line: number; end_line: number;
  excerpt: string; truncated: boolean; github_url: string;
};
export type SemanticResults = { repository_id: number; commit_sha: string; query: string; model: string; items: SemanticHit[] };
export type CitedAnswer = {
  question: string; commit_sha: string; answer: string; mode: "source_findings" | "generated"; notice: string | null;
  citations: {id: number; title: string; path: string; file_id: number; symbol: SymbolRecord | null;
    start_line: number; end_line: number; github_url: string; quote: string; quote_truncated: boolean}[];
};
export type ImpactReport = {
  commit_sha: string; affected_file_count: number; affected_symbol_count: number; scope: string;
  scope_rule: string; truncated: boolean; unresolved_imports: number; unresolved_calls: number;
  files: {file_id: number; path: string; depth: number; is_test: boolean}[];
  symbols: {symbol: SymbolRecord; path: string; depth: number}[]; limitations: string[];
};
export type ArchitectureFile = {file_id: number; path: string; fan_in: number; fan_out: number;
  centrality: number; branch_points: number | null; review_score: number | null};
export type ArchitectureReport = {
  commit_sha: string; file_count: number; dependency_pairs: number; isolated_files: number;
  cycle_component_count: number; cyclic_files: number; unresolved_imports: number; parse_error_files: number;
  hubs: ArchitectureFile[]; hotspots: ArchitectureFile[]; hotspot_rule: string;
  cycles: {files: {file_id: number; path: string}[]; size: number; truncated: boolean}[];
  cycles_truncated: boolean; limitations: string[];
};
export type SearchPage = {
  repository_id: number;
  query: string;
  parsed: boolean;
  commit_sha: string | null;
  items: SearchHit[];
  total: number;
  limit: number;
  offset: number;
};
export type SymbolDetail = {
  symbol: SymbolRecord;
  file: SourceFile;
  source: string;
  commit_sha: string;
  github_url: string;
  has_parse_errors: boolean;
};
export type SourceSelection = {
  symbol: SymbolRecord;
  commit_sha: string;
  request: number;
};

export type RelationshipPage = {
  ready: boolean;
  commit_sha: string | null;
  total: number;
  offset: number;
  limit: number;
  items: {
    id: number;
    kind: string;
    resolution: string;
    source_name: string;
    target_name: string;
    file_id: number;
    path: string;
    start_line: number;
    target_file_id: number | null;
    target_path: string | null;
  }[];
};

export type DependencyGraph = {
  file_id: number;
  ready: boolean;
  commit_sha: string | null;
  total_neighbors: number;
  unresolved_imports: number;
  self_imports: number;
  nodes: { id: number; path: string }[];
  edges: { source: number; target: number; count: number }[];
};

export type CallPage = {
  file_id: number;
  ready: boolean;
  commit_sha: string | null;
  has_parse_errors: boolean;
  summary: { total: number; candidates: number; ambiguous: number; unresolved: number };
  items: { id: number; expression: string; call_type: string; start_line: number;
    end_line: number; column: number; resolution: string;
    caller: SymbolRecord | null; target: SymbolRecord | null }[];
  total: number;
  limit: number;
  offset: number;
};
