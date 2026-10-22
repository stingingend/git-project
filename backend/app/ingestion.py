"""Clone public GitHub repositories and read source without a working tree."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
import re
from pathlib import Path, PurePosixPath
import signal
import subprocess
import tempfile
import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Repository, RepositorySnapshot, SourceFile, IndexChanges
from .parsing import clear_file_results, invalidate_snapshot
from .schemas import RepositoryCreate
from .languages import language_for_path

IGNORED_DIRECTORIES = {
    ".git", "node_modules", "dist", "build", "vendor", "venv", ".venv",
    "__pycache__", "coverage", ".tox", ".mypy_cache", ".pytest_cache",
    ".next", ".nuxt", ".output", "out", ".turbo",
}


@dataclass(frozen=True)
class Limits:
    clone_seconds: float = 90
    clone_bytes: int = 150 * 1024 * 1024
    max_files: int = 2000
    max_tracked_files: int = 20000
    file_bytes: int = 1024 * 1024
    source_bytes: int = 25 * 1024 * 1024


class IngestionError(ValueError):
    pass


def git_environment() -> dict[str, str]:
    # Public-only ingestion must not use saved credentials or custom Git config.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ALLOW_PROTOCOL": "https",
        "GIT_LFS_SKIP_SMUDGE": "1", "GIT_ASKPASS": "", "GCM_INTERACTIVE": "never",
    })
    return env


def git_command(*args: str) -> list[str]:
    return ["git", "-c", "credential.helper=", "-c", "http.followRedirects=false", *args]


def read_git(path: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            git_command("-C", str(path), *args), env=git_environment(),
            check=True, capture_output=True, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise IngestionError("Unable to read repository metadata or source.") from exc


def directory_size(path: Path) -> int:
    size = 0
    for file in path.rglob("*"):
        try:
            if file.is_file():
                size += file.stat().st_size
        except FileNotFoundError:
            # Git can rename temporary pack/lock files between discovery and stat.
            continue
    return size


def stop_clone(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # Git launches transport children; stop the tree before removing its files.
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


@contextmanager
def clone_repository(github_url: str, limits: Limits = Limits(), commit_sha: str | None = None):
    # Validate again at the network boundary, even for records already in storage.
    url = RepositoryCreate(github_url=github_url).github_url
    if commit_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise IngestionError("Requested revision must be a full lowercase Git commit SHA.")
    with tempfile.TemporaryDirectory(prefix="codeatlas-") as directory:
        root = Path(directory)
        destination = root / "repo"
        if commit_sha:
            destination.mkdir()
            read_git(destination, "init", "--bare")
            read_git(destination, "remote", "add", "origin", url)
            command = git_command("-C", str(destination), "fetch", "--depth=1", "--no-tags", "origin", commit_sha)
        else:
            command = git_command("clone", "--depth=1", "--single-branch", "--no-tags",
                                  "--no-checkout", "--", url, str(destination))
        try:
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(
                    command,
                    env=git_environment(), stdout=subprocess.DEVNULL, stderr=errors,
                    start_new_session=os.name != "nt",
                )
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        if time.monotonic() - started > limits.clone_seconds:
                            raise IngestionError("Clone exceeded its time limit.")
                        if directory_size(root) > limits.clone_bytes:
                            raise IngestionError("Repository exceeds the clone storage limit.")
                        time.sleep(0.1)
                    if process.returncode:
                        raise IngestionError("Clone failed. Check that the repository exists and is public.")
                    if directory_size(root) > limits.clone_bytes:
                        raise IngestionError("Repository exceeds the clone storage limit.")
                finally:
                    stop_clone(process)
        except FileNotFoundError as exc:
            raise IngestionError("Git must be installed on the API server.") from exc
        if commit_sha:
            read_git(destination, "update-ref", "HEAD", "FETCH_HEAD")
            actual = read_git(destination, "rev-parse", "HEAD").decode("ascii").strip()
            if actual != commit_sha:
                raise IngestionError("Git returned a different commit than requested.")
        yield destination


@dataclass
class DiscoveredFile:
    path: str
    source: str
    content_hash: str
    line_count: int
    language: str


def discover_source_files(path: Path, limits: Limits = Limits()) -> tuple[list[DiscoveredFile], int]:
    entries = read_git(path, "ls-tree", "--full-tree", "-rlz", "HEAD").split(b"\0")
    if len(entries) - 1 > limits.max_tracked_files:
        raise IngestionError("Repository exceeds the tracked file limit.")
    files = []
    skipped = 0
    total_bytes = 0
    eligible_files = 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        if not language_for_path(raw_path.decode("utf-8", errors="replace")):
            continue
        mode, kind, blob_sha, size = metadata.split()
        try:
            file_path = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue
        if (mode not in {b"100644", b"100755"} or kind != b"blob"
                or any(part in IGNORED_DIRECTORIES for part in PurePosixPath(file_path).parts[:-1])):
            skipped += 1
            continue
        if int(size) > limits.file_bytes:
            skipped += 1
            continue
        eligible_files += 1
        total_bytes += int(size)
        if eligible_files > limits.max_files or total_bytes > limits.source_bytes:
            raise IngestionError("Repository exceeds the supported-source file count or source size limit.")
        content = read_git(path, "cat-file", "blob", blob_sha.decode("ascii"))
        try:
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            skipped += 1
            continue
        files.append(DiscoveredFile(file_path, source, hashlib.sha256(content).hexdigest(),
                                    len(source.splitlines()), language_for_path(file_path, source)))
    return files, skipped


def ingest_repository(session: Session, repository: Repository, limits: Limits = Limits(),
                      commit_sha: str | None = None) -> RepositorySnapshot:
    clone = clone_repository(repository.github_url, limits, commit_sha) if commit_sha else clone_repository(repository.github_url, limits)
    with clone as path:
        files, skipped = discover_source_files(path, limits)
        sha = read_git(path, "rev-parse", "HEAD").decode("ascii").strip()
        branch = "commit" if commit_sha else read_git(path, "symbolic-ref", "--short", "HEAD").decode("utf-8").strip()

    # Diff after clone cleanup; unchanged source and index identities survive.
    existing = {file.path: file for file in session.scalars(select(SourceFile).where(
        SourceFile.repository_id == repository.id))}
    discovered = {file.path: file for file in files}
    removed = set(existing) - set(discovered)
    added = set(discovered) - set(existing)
    changed = {path for path in set(existing) & set(discovered)
               if existing[path].content_hash != discovered[path].content_hash}
    invalidate_snapshot(session, repository.id)
    clear_file_results(session, [existing[path].id for path in removed | changed])
    for path in removed:
        session.delete(existing[path])
    for path in changed:
        saved, fresh = existing[path], discovered[path]
        saved.source, saved.content_hash, saved.line_count = fresh.source, fresh.content_hash, fresh.line_count
        saved.language = fresh.language
    for path in (set(existing) & set(discovered)) - changed:
        existing[path].language = discovered[path].language
    changes = session.get(IndexChanges, repository.id)
    if changes is None:
        changes = IndexChanges(repository_id=repository.id)
        session.add(changes)
    changes.added, changes.changed, changes.removed = len(added), len(changed), len(removed)
    changes.unchanged = len(files) - len(added) - len(changed)
    changes.parsed_files = changes.reused_files = None
    snapshot = session.get(RepositorySnapshot, repository.id)
    if snapshot is None:
        snapshot = RepositorySnapshot(repository_id=repository.id)
        session.add(snapshot)
    snapshot.commit_sha = sha
    snapshot.default_branch = branch
    snapshot.ingested_at = datetime.now(timezone.utc)
    snapshot.file_count = len(files)
    snapshot.skipped_files = skipped
    snapshot.line_count = sum(file.line_count for file in files)
    session.add_all([
        SourceFile(repository_id=repository.id, path=file.path, language=file.language, source=file.source,
                   content_hash=file.content_hash, line_count=file.line_count)
        for file in files if file.path in added
    ])
    repository.status = "ingested"
    session.flush()
    return snapshot
