import type {
  FileDetail,
  Overview,
  Repository,
  SourceFile,
  Stage,
  SearchPage,
  SearchHit,
  SymbolDetail,
  RelationshipPage,
  DependencyGraph,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function createApi(fetcher: typeof fetch = fetch) {
  async function request<T>(path: string, options?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetcher(`/api${path}`, {
        cache: "no-store",
        ...options,
      });
    } catch {
      throw new ApiError(
        "Cannot reach CodeAtlas. Check that the web server and API are running.",
        0,
      );
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((item) => String(item.msg).replace(/^Value error, /, ""))
                .join(" ")
            : "The API is unavailable. Check that the backend is running, then try again.";
      throw new ApiError(message, response.status);
    }
    if (body === null)
      throw new ApiError(
        "The API returned an unreadable response. Try again.",
        response.status,
      );
    return body as T;
  }
  return {
    repositories: () => request<Repository[]>("/repositories"),
    register: (github_url: string) =>
      request<Repository>("/repositories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url }),
      }),
    ingest: (id: number) =>
      request(`/repositories/${id}/ingest`, { method: "POST" }),
    parse: (id: number) =>
      request(`/repositories/${id}/parse`, { method: "POST" }),
    overview: (id: number) => request<Overview>(`/repositories/${id}/overview`),
    files: (id: number) => request<SourceFile[]>(`/repositories/${id}/files`),
    file: (id: number, fileId: number, offset = 0) =>
      request<FileDetail>(
        `/repositories/${id}/files/${fileId}?limit=100&offset=${offset}`,
      ),
    search: (id: number, query: string, kind = "", offset = 0) => {
      const params = new URLSearchParams({
        q: query,
        limit: "20",
        offset: String(offset),
      });
      if (kind) params.set("kind", kind);
      return request<SearchPage>(`/repositories/${id}/search?${params}`);
    },
    symbol: (id: number, symbolId: number) =>
      request<SymbolDetail>(`/repositories/${id}/symbols/${symbolId}`),
    graph: (id: number, fileId: number) =>
      request<DependencyGraph>(`/repositories/${id}/files/${fileId}/graph`),
    relationships: (id: number, fileId: number, kind: string, direction: string, offset = 0) => {
      const params = new URLSearchParams({ direction, limit: "30", offset: String(offset) });
      if (kind) params.set("kind", kind);
      return request<RelationshipPage>(`/repositories/${id}/files/${fileId}/relationships?${params}`);
    },
  };
}

export type Api = ReturnType<typeof createApi>;

export async function loadSymbolSource(
  api: Api,
  repositoryId: number,
  hit: SearchHit,
  commitSha: string,
) {
  const selected = await api.symbol(repositoryId, hit.symbol.id);
  const current = selected.symbol;
  if (
    selected.commit_sha !== commitSha ||
    current.file_id !== hit.symbol.file_id ||
    current.qualified_name !== hit.symbol.qualified_name ||
    current.start_line !== hit.symbol.start_line ||
    current.end_line !== hit.symbol.end_line ||
    selected.file.path !== hit.path
  ) {
    throw new ApiError(
      "The index changed. Refresh the repository and search again.",
      409,
    );
  }
  const detail = await api.file(repositoryId, current.file_id);
  if (detail.commit_sha !== commitSha || detail.file.path !== hit.path) {
    throw new ApiError(
      "The index changed. Refresh the repository and search again.",
      409,
    );
  }
  return { detail, symbol: current, commit_sha: commitSha };
}

export async function indexRepository(
  url: string,
  api: Api,
  progress: (stage: Stage, repository?: Repository) => void,
): Promise<Repository> {
  progress("registering");
  let repository: Repository;
  try {
    repository = await api.register(url.trim());
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error;
    const canonical = url
      .trim()
      .replace(/\/$/, "")
      .replace(/\.git$/, "")
      .toLowerCase();
    const existing = (await api.repositories()).find(
      (repo) => repo.github_url === canonical,
    );
    if (!existing) throw error;
    repository = existing;
  }
  progress("ingesting", repository);
  await api.ingest(repository.id);
  progress("parsing", repository);
  await api.parse(repository.id);
  return repository;
}
