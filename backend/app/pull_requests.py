"""Public, read-only GitHub PR reports with durable local execution records."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import re
import threading
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from sqlalchemy import select, update

from .analysis import impact
from .answers import NoRedirect
from .database import begin_read_snapshot
from .jobs import IndexingBusy
from .models import ParseSnapshot, PullRequestReport, Repository, RepositorySnapshot, SourceFile, Symbol

logger = logging.getLogger(__name__)
MAX_FILES = 500
ACTIVE = ("queued", "running")


class PullRequestError(ValueError):
    pass


def github_json(path):
    request = Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CodeAtlas-public-repository-analysis"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise PullRequestError("GitHub response exceeds the size limit.")
        return json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PullRequestError("Could not read this public PR. Check its number and GitHub availability/rate limits.") from exc


def fetch_pull_request(owner, name, number):
    path = f"/repos/{owner}/{name}/pulls/{number}"
    metadata = github_json(path)
    try:
        base, head, count = metadata["base"]["sha"], metadata["head"]["sha"], metadata["changed_files"]
        if metadata["base"]["repo"]["private"]:
            raise PullRequestError("Only public pull requests are supported.")
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base, head)):
            raise PullRequestError("GitHub returned an unsupported revision.")
        if type(count) is not int or not 0 <= count <= MAX_FILES:
            raise PullRequestError(f"PR analysis is limited to {MAX_FILES} changed files.")
        files = []
        for page in range(1, (count + 99) // 100 + 1):
            batch = github_json(f"{path}/files?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise PullRequestError("GitHub returned an invalid file list.")
            files.extend(batch)
        latest = github_json(path)
        if latest["base"]["sha"] != base or latest["head"]["sha"] != head or len(files) != count:
            raise PullRequestError("The PR changed while loading. Retry the analysis.")
        return dict(number=number, title=str(metadata["title"])[:500], base_sha=base, head_sha=head,
                    github_url=f"https://github.com/{owner}/{name}/pull/{number}", files=files)
    except (KeyError, TypeError) as exc:
        raise PullRequestError("GitHub returned incomplete PR metadata.") from exc


def changed_base_lines(patch):
    """Unified diff metadata, never source parsing; additions include both anchors."""
    lines, cursor = set(), None
    for line in patch.split("\n"):
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
            cursor = int(match.group(1)) if match else None
        elif cursor is not None and line.startswith("-"):
            lines.add(max(1, cursor)); cursor += 1
        elif cursor is not None and line.startswith("+"):
            lines.update((max(1, cursor), max(1, cursor - 1)))
        elif cursor is not None and line.startswith(" "):
            cursor += 1
    return lines


def analyze_pull_request(session, repository_id, payload):
    snapshot = session.get(RepositorySnapshot, repository_id)
    parsed = session.get(ParseSnapshot, repository_id)
    comparable = snapshot is not None and parsed is not None and snapshot.commit_sha == parsed.commit_sha == payload["base_sha"]
    base = {key: value for key, value in payload.items() if key != "files"}
    base.update(commit_sha=snapshot.commit_sha if snapshot else None, comparable=comparable,
                requires_base_index=not comparable, changed_file_count=len(payload["files"]))
    files = {file.path: file for file in session.scalars(select(SourceFile).where(SourceFile.repository_id == repository_id))}
    symbols = defaultdict_symbols(session, files)
    changed, touched, changed_files = [], set(), set()
    for item in payload["files"]:
        path = str(item.get("filename", ""))[:4096]
        old_path = str(item.get("previous_filename", path))[:4096]
        file = files.get(old_path)
        patch = item.get("patch")
        relevant = path.endswith(".py") or old_path.endswith(".py")
        available = isinstance(patch, str) and len(patch) <= 1_000_000
        matched = []
        if comparable and file is not None and relevant:
            changed_files.add(file.id)
            points = changed_base_lines(patch) if available else set()
            whole_file = item.get("status") in {"removed", "renamed"} or not available
            matched = [symbol.id for symbol in symbols[file.id]
                       if whole_file or any(symbol.start_line <= line <= symbol.end_line for line in points)]
            touched.update(matched)
        changed.append(dict(path=path, previous_path=old_path if old_path != path else None,
            status=str(item.get("status", "unknown")), additions=int(item.get("additions", 0)),
            deletions=int(item.get("deletions", 0)), indexed=file is not None, supported=relevant,
            patch_available=available, changed_symbol_ids=matched[:100], symbols_truncated=len(matched) > 100))
    base.update(files=changed, changed_symbol_count=len(touched), changed_symbol_ids=sorted(touched)[:1000],
                symbols_truncated=len(touched) > 1000, impact=None)
    if comparable and (changed_files or touched):
        base["impact"] = impact(session, repository_id, changed_files, sorted(touched)[:1000],
                                seed_all_file_symbols=False)
    base["limitations"] = ["PR mapping uses old-side diff lines against the exact base commit.",
        "Missing patches conservatively select all definitions in an indexed file; additions use adjacent anchors.",
        "New/unindexed files and unsupported languages have no known reverse dependencies in this index.",
        "Impact follows static candidates and does not prove runtime breakage."]
    return base


def defaultdict_symbols(session, files):
    result = {file.id: [] for file in files.values()}
    for symbol in session.scalars(select(Symbol).where(Symbol.file_id.in_(result), Symbol.symbol_type != "import")):
        result[symbol.file_id].append(symbol)
    return result


def report_read(report):
    return dict(id=report.id, repository_id=report.repository_id, number=report.number, status=report.status,
        created_at=report.created_at.replace(tzinfo=timezone.utc) if report.created_at.tzinfo is None else report.created_at,
        finished_at=report.finished_at.replace(tzinfo=timezone.utc) if report.finished_at and report.finished_at.tzinfo is None else report.finished_at,
        error=report.error, result=json.loads(report.result) if report.result else None)


class PullRequestWorker:
    def __init__(self, sessions):
        self.sessions = sessions
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="codeatlas-pr")

    def recover(self):
        with self.sessions() as session:
            session.execute(update(PullRequestReport).where(PullRequestReport.status.in_(ACTIVE)).values(
                status="interrupted", finished_at=datetime.now(timezone.utc), error="API restarted. Run PR analysis again."))
            session.commit()

    def submit(self, repository_id, number, delivery_id=None):
        with self.sessions() as session:
            if delivery_id:
                existing = session.scalar(select(PullRequestReport).where(PullRequestReport.delivery_id == delivery_id))
                if existing:
                    return report_read(existing)
        if not self.lock.acquire(blocking=False):
            raise IndexingBusy("A PR report is already running. Retry when it finishes.")
        report_id = str(uuid.uuid4())
        try:
            with self.sessions() as session:
                report = PullRequestReport(id=report_id, repository_id=repository_id, number=number,
                    delivery_id=delivery_id, status="queued", created_at=datetime.now(timezone.utc))
                session.add(report); session.commit()
                result = report_read(report)
            self.executor.submit(self.run, report_id)
            return result
        except Exception:
            try:
                self.finish(report_id, error="The PR worker could not start. Try again.")
            finally:
                self.lock.release()
            raise

    def finish(self, report_id, result=None, error=None):
        with self.sessions() as session:
            report = session.get(PullRequestReport, report_id)
            if report:
                report.status = "failed" if error else "succeeded"
                report.error, report.finished_at = error, datetime.now(timezone.utc)
                report.result = json.dumps(result) if result is not None else None
                session.commit()

    def run(self, report_id):
        try:
            with self.sessions() as session:
                report = session.get(PullRequestReport, report_id)
                repository_id, number = report.repository_id, report.number
                repository = session.get(Repository, repository_id)
                owner, name = repository.owner, repository.name
                report.status = "running"; session.commit()
            payload = fetch_pull_request(owner, name, number)
            with self.sessions() as session:
                begin_read_snapshot(session)
                result = analyze_pull_request(session, repository_id, payload)
            self.finish(report_id, result=result)
        except Exception as exc:
            logger.exception("PR analysis failed")
            try:
                self.finish(report_id, error=str(exc) if isinstance(exc, PullRequestError) else "PR analysis failed. Check API logs and retry.")
            except Exception:
                logger.exception("Could not persist PR failure")
        finally:
            self.lock.release()

    def close(self):
        self.executor.shutdown(wait=True)
