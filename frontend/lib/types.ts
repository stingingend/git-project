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
export type Stage = "registering" | "ingesting" | "parsing";
