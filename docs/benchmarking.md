# Phase 21: reproducible measurements

Run from the repository root after installing the backend:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_index.py --files 100 --changed 4 --repeat 3 --semantic --output docs/benchmark-latest.json
```

The script creates its own temporary Git repository and SQLite database. Each file has twenty synthetic functions and a dependency on its predecessor. Three rounds modify four of one hundred files. It measures source discovery/persistence separately, checks that exactly four files parse and ninety-six reuse their indexes, and verifies unchanged symbol IDs. It then forces full extraction by invalidating the cache format. No user index is cleared and no source code executes.

The committed [raw run](benchmark-latest.json) used Windows, Python 3.12.14, SQLite, 100 files, 2,099 symbols including imports, and 4,499 lines:

| Measurement | Median |
| --- | ---: |
| Full syntax parse and publication | 365 ms |
| Incremental parse and publication | 143 ms |
| Measured parsing/publication speedup | 2.56× |
| Files reused per incremental round | 96/100 |
| Literal symbol query | 4.18 ms |
| Semantic query over 2,100 units | 213 ms |

The local semantic model loaded in 707 ms and embedding construction took 684 ms in this run. Those are single measurements, not medians. The weights were already cached.

Network cloning is excluded by substituting the already-created local Git fixture at the clone boundary. Source discovery/persistence still took roughly 2.6 seconds on this Windows run, largely from per-blob Git subprocesses. The parse speedup covers parsing/publication. Query measurements invoke the query layer directly; they exclude HTTP, browser rendering, and concurrent load.

Results vary by machine, database, source layout, repository size, and cache state. The fixture measures repeatability and reuse correctness, not production throughput or retrieval relevance. Bounds remain enforced. CI runs a small six-file/two-change fixture without fragile timing thresholds. For larger investigations, vary `--files` up to 2,000 and keep `--changed` smaller than that count.
