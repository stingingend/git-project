import type { IndexChanges } from "../lib/types";

export function IndexChangesView({ changes }: { changes: IndexChanges }) {
  return <div className="index-changes" aria-label="Indexing changes">
    <div className="change-counts">
      <span><strong>{changes.added}</strong> added</span>
      <span><strong>{changes.changed}</strong> changed</span>
      <span><strong>{changes.removed}</strong> removed</span>
      <span><strong>{changes.unchanged}</strong> unchanged</span>
    </div>
    <p>{changes.parsed_files === null || changes.reused_files === null
      ? "Comparing saved source. Parse results pending."
      : `${changes.parsed_files} files parsed · ${changes.reused_files} saved file indexes reused`}</p>
  </div>;
}
