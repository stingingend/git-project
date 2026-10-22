"""Reproducible local Git/SQLite benchmark; never touches the user's index."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time
from unittest.mock import patch

from sqlalchemy import select

from app.database import create_database
from app.ingestion import ingest_repository
from app.index import search_symbols
from app.migrations import upgrade_database
from app.models import IndexChanges, Repository, SourceFile, Symbol
from app import parsing
from app.parsing import parse_repository


def timed(operation):
    started = time.perf_counter()
    result = operation()
    return result, time.perf_counter() - started


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null",
        "-c", "user.name=Benchmark", "-c", "user.email=benchmark@example.invalid", *arguments],
        check=True, capture_output=True).stdout


def source(index, revision):
    lines = [f"# synthetic module {index}, revision {revision}"]
    if index:
        lines.append(f"from module_{index - 1} import action_0 as previous")
    lines += ["def action_0(value):", '    """Validate and transform a synthetic input value."""',
              "    if value:", "        return value + 1", "    return 0"]
    for number in range(1, 20):
        lines += [f"def action_{number}(value):", f"    return action_{number - 1}(value)"]
    return "\n".join(lines) + "\n"


def benchmark(files=100, changed=4, repeat=3, semantic=False):
    original_version = parsing.INDEX_FORMAT_VERSION
    try:
        with tempfile.TemporaryDirectory(prefix="codeatlas-benchmark-") as directory:
            root = Path(directory)
            fixture = root / "fixture"
            fixture.mkdir()
            git(fixture, "init", "-b", "main")
            for index in range(files):
                (fixture / f"module_{index}.py").write_text(source(index, 0), encoding="utf-8")
            git(fixture, "add", "."); git(fixture, "commit", "-m", "synthetic baseline")
            engine, sessions = create_database(f"sqlite:///{(root / 'benchmark.db').as_posix()}")
            try:
                upgrade_database(engine)

                @contextmanager
                def local_clone(*_):
                    yield fixture

                full, incremental, ingestion, runs = [], [], [], []
                with sessions() as session, patch("app.ingestion.clone_repository", local_clone):
                    repo = Repository(github_url="https://github.com/example/benchmark", owner="example", name="benchmark")
                    session.add(repo); session.commit()
                    ingest_repository(session, repo); session.commit()
                    parse_repository(session, repo); session.commit()
                    unchanged_path = f"module_{files - 1}.py"
                    def ids():
                        file = session.scalar(select(SourceFile).where(SourceFile.path == unchanged_path))
                        return file.id, list(session.scalars(select(Symbol.id).where(Symbol.file_id == file.id).order_by(Symbol.id)))
                    for round_index in range(repeat):
                        before = ids()
                        for index in range(changed):
                            (fixture / f"module_{index}.py").write_text(source(index, round_index + 1), encoding="utf-8")
                        git(fixture, "add", "."); git(fixture, "commit", "-m", f"change {changed} files, round {round_index + 1}")
                        def ingest():
                            ingest_repository(session, repo); session.commit()
                        def parse():
                            parsed = parse_repository(session, repo); session.commit(); return parsed
                        _, ingest_seconds = timed(ingest)
                        parsed, incremental_seconds = timed(parse)
                        changes = session.get(IndexChanges, repo.id)
                        if changes.parsed_files != changed or changes.reused_files != files - changed or ids() != before:
                            raise AssertionError("Incremental counts or unchanged IDs are incorrect")
                        runs.append(dict(parsed=changes.parsed_files, reused=changes.reused_files,
                                         commit_sha=parsed.commit_sha, unchanged_ids_preserved=True))
                        incremental.append(incremental_seconds); ingestion.append(ingest_seconds)
                        # Force full syntax extraction with a cache-format invalidation.
                        # Keep that format active for the next incremental run.
                        parsing.INDEX_FORMAT_VERSION = f"benchmark-full-{round_index}"
                        parsed, seconds = timed(parse)
                        full.append(seconds)
                    latency = []
                    for _ in range(30):
                        _, seconds = timed(lambda: search_symbols(session, repo.id, "action_19", None, 20, 0))
                        latency.append(seconds)
                    result = dict(timestamp=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                        os=platform.system(), storage="SQLite", files=files, changed_files=changed, repeat=repeat,
                        symbols=parsed.symbol_count, lines=sum(file.line_count for file in session.scalars(select(SourceFile))),
                        full_parse_seconds=full, incremental_parse_seconds=incremental, discovery_persistence_seconds=ingestion,
                        median_full_parse_seconds=statistics.median(full), median_incremental_parse_seconds=statistics.median(incremental),
                        measured_parse_speedup=statistics.median(full) / statistics.median(incremental),
                        median_symbol_query_seconds=statistics.median(latency), runs=runs,
                        methodology="Synthetic local Git revisions; network clone excluded. Parse/publication measured separately from discovery. Full runs invalidate the syntax cache format. No repository code executes.")
                    if semantic:
                        from app.semantic import build_semantic_index, encode, semantic_search
                        _, cold_seconds = timed(lambda: encode(["warm up local embeddings"]))
                        def build():
                            indexed = build_semantic_index(session, repo.id); session.commit(); return indexed
                        indexed, build_seconds = timed(build)
                        queries = [timed(lambda: semantic_search(session, repo.id, "validate an input value", 5))[1] for _ in range(10)]
                        result["semantic"] = dict(model_load_seconds=cold_seconds, build_seconds=build_seconds,
                            document_count=indexed["document_count"], median_query_seconds=statistics.median(queries))
            finally:
                engine.dispose()
            return result
    finally:
        parsing.INDEX_FORMAT_VERSION = original_version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=100)
    parser.add_argument("--changed", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.changed < args.files <= 2000 or not 1 <= args.repeat <= 20:
        parser.error("Use 1 <= changed < files <= 2000 and 1 <= repeat <= 20")
    result = benchmark(args.files, args.changed, args.repeat, args.semantic)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
