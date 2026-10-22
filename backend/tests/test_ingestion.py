from contextlib import contextmanager
import hashlib
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import ingestion
from app.ingestion import IngestionError, Limits, clone_repository, discover_source_files
from app.main import create_app
from app.models import SourceFile


@pytest.fixture
def git_repository(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/app.py").write_bytes(b"raise RuntimeError('source must never execute')\n")
    (root / "src/empty.py").write_bytes(b"")
    (root / "src/bom.py").write_bytes(b"\xef\xbb\xbf# UTF-8 BOM\n")
    (root / "src/legacy.py").write_bytes(b"# invalid UTF-8: \xff")
    (root / "vendor").mkdir()
    (root / "vendor/generated.py").write_bytes(b"# ignored\n")
    (root / "README.md").write_bytes(b"not Python")
    def git(*args, input=None):
        return subprocess.run(["git", "-C", str(root), *args], input=input,
                              capture_output=True, check=True).stdout
    git("init", "-b", "main")
    git("add", ".")
    # A Git symlink entry works on Windows without OS symlink permissions.
    blob = git("hash-object", "-w", "--stdin", input=b"src/app.py").decode().strip()
    git("update-index", "--add", "--cacheinfo", f"120000,{blob},link.py")
    git("-c", "core.hooksPath=/dev/null", "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-m", "fixture")
    return root


@pytest.fixture
def local_clone(git_repository, monkeypatch):
    @contextmanager
    def fake_clone(url, limits=Limits()):
        yield git_repository
    monkeypatch.setattr(ingestion, "clone_repository", fake_clone)


def register(client):
    response = client.post("/repositories", json={"github_url": "https://github.com/example/demo"})
    assert response.status_code == 201
    return response.json()["id"]


def test_discovery_excludes_vendor_symlinks_and_unsupported_encodings(git_repository):
    files, skipped = discover_source_files(git_repository)
    assert [file.path for file in files] == ["src/app.py", "src/bom.py", "src/empty.py"]
    assert skipped == 3
    assert files[0].line_count == 1
    assert files[0].content_hash == hashlib.sha256((git_repository / "src/app.py").read_bytes()).hexdigest()
    assert files[1].source == "# UTF-8 BOM\n"
    assert files[2].line_count == 0


@pytest.mark.parametrize("limits", [Limits(max_files=1), Limits(source_bytes=1), Limits(max_tracked_files=1)])
def test_discovery_rejects_repository_limits(git_repository, limits):
    with pytest.raises(IngestionError, match="limit"):
        discover_source_files(git_repository, limits)


def test_oversized_individual_files_are_skipped(git_repository):
    files, skipped = discover_source_files(git_repository, Limits(file_bytes=1))
    assert [file.path for file in files] == ["src/empty.py"]
    assert skipped == 5


def test_ingestion_endpoints_persist_and_replace_snapshot(client, local_clone):
    repository_id = register(client)
    prefix = f"/repositories/{repository_id}"
    assert client.get(prefix + "/snapshot").status_code == 404
    assert client.get(prefix + "/files").json() == []
    response = client.post(prefix + "/ingest")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["repository_id"] == repository_id
    assert snapshot["file_count"] == 3
    assert snapshot["skipped_files"] == 3
    assert snapshot["line_count"] == 2
    assert snapshot["default_branch"] == "main"
    assert len(snapshot["commit_sha"]) == 40
    assert snapshot["ingested_at"].endswith("Z")
    assert client.get(prefix).json()["status"] == "ingested"
    assert client.get(prefix + "/snapshot").json() == snapshot
    files = client.get(prefix + "/files").json()
    assert len(files) == 3
    assert all(file["language"] == "Python" and "source" not in file for file in files)
    assert client.post(prefix + "/ingest").status_code == 200
    assert len(client.get(prefix + "/files").json()) == 3
    with client.app.state.sessions() as session:
        source = session.scalar(select(SourceFile).where(SourceFile.path == "src/app.py"))
        assert source.source.startswith("raise RuntimeError")


def test_snapshot_survives_restart(database_url, local_clone):
    with TestClient(create_app(database_url)) as first:
        repository_id = register(first)
        snapshot = first.post(f"/repositories/{repository_id}/ingest").json()
    with TestClient(create_app(database_url)) as second:
        assert second.get(f"/repositories/{repository_id}/snapshot").json() == snapshot
        assert len(second.get(f"/repositories/{repository_id}/files").json()) == 3


def test_reingestion_invalidates_snapshot_but_preserves_unchanged_symbols(client, local_clone, git_repository):
    (git_repository / "src/app.py").write_bytes(b"def hello():\n    return True\n")
    subprocess.run(["git", "-C", str(git_repository), "-c", "user.name=Test",
                    "-c", "user.email=test@example.com", "commit", "-am", "add definition"],
                   check=True, capture_output=True)
    repository_id = register(client)
    prefix = f"/repositories/{repository_id}"
    assert client.post(prefix + "/ingest").status_code == 200
    assert client.post(prefix + "/parse").status_code == 200
    assert len(client.get(prefix + "/symbols").json()) == 1
    assert client.get(prefix + "/search", params={"q": "hello"}).json()["total"] == 1
    assert client.get(prefix + "/parse").status_code == 200
    assert client.post(prefix + "/ingest").status_code == 200
    assert client.get(prefix + "/parse").status_code == 404
    assert client.get(prefix + "/parse/files").status_code == 404
    assert len(client.get(prefix + "/symbols").json()) == 1
    search = client.get(prefix + "/search", params={"q": "hello"}).json()
    assert search["parsed"] is False and search["items"] == []
    assert client.get(prefix).json()["status"] == "ingested"


def test_failed_reingestion_preserves_previous_snapshot(client, local_clone, monkeypatch):
    repository_id = register(client)
    prefix = f"/repositories/{repository_id}"
    snapshot = client.post(prefix + "/ingest").json()
    files = client.get(prefix + "/files").json()
    @contextmanager
    def fail(url, limits):
        raise IngestionError("Clone failed.")
        yield
    monkeypatch.setattr(ingestion, "clone_repository", fail)
    assert client.post(prefix + "/ingest").status_code == 422
    assert client.get(prefix + "/snapshot").json() == snapshot
    assert client.get(prefix + "/files").json() == files
    assert client.get(prefix).json()["status"] == "ingested"


def test_failed_first_ingestion_leaves_repository_registered(client, monkeypatch):
    repository_id = register(client)
    @contextmanager
    def fail(url, limits):
        raise IngestionError("Clone failed.")
        yield
    monkeypatch.setattr(ingestion, "clone_repository", fail)
    assert client.post(f"/repositories/{repository_id}/ingest").status_code == 422
    assert client.get(f"/repositories/{repository_id}").json()["status"] == "registered"
    assert client.get(f"/repositories/{repository_id}/files").json() == []
    assert not client.app.state.ingestion_lock.locked()


def test_database_write_failure_rolls_back_snapshot_replacement(client, local_clone, git_repository):
    repository_id = register(client)
    prefix = f"/repositories/{repository_id}"
    snapshot = client.post(prefix + "/ingest").json()
    parsed = client.post(prefix + "/parse").json()
    files = client.get(prefix + "/files").json()
    (git_repository / "new.py").write_text("def added(): return True\n")
    subprocess.run(["git", "-C", str(git_repository), "add", "new.py"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(git_repository), "-c", "user.name=Test",
                    "-c", "user.email=test@example.com", "commit", "-m", "add source"],
                   check=True, capture_output=True)
    engine = client.app.state.sessions.kw["bind"]
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_source BEFORE INSERT ON source_files "
            "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
        )
    try:
        with pytest.raises(IntegrityError):
            client.post(prefix + "/ingest")
        assert client.get(prefix + "/files").json() == files
        assert client.get(prefix + "/snapshot").json() == snapshot
        assert client.get(prefix).json()["status"] == "parsed"
        assert client.get(prefix + "/parse").json() == parsed
        assert not client.app.state.ingestion_lock.locked()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER reject_source")


def test_ingestion_lock_and_missing_records(client):
    repository_id = register(client)
    with client.app.state.ingestion_lock:
        assert client.post(f"/repositories/{repository_id}/ingest").status_code == 409
    for path in ["ingest", "snapshot", "files"]:
        response = client.post(f"/repositories/999/{path}") if path == "ingest" else client.get(f"/repositories/999/{path}")
        assert response.status_code == 404


@pytest.fixture
def fake_transport(monkeypatch):
    calls = []
    class Process:
        returncode = 0
        def poll(self):
            return self.returncode
    process = Process()
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).mkdir()
        return process
    def stop(value):
        value.returncode = -9 if value.returncode is None else value.returncode
    monkeypatch.setattr(ingestion.subprocess, "Popen", popen)
    monkeypatch.setattr(ingestion, "stop_clone", stop)
    return process, calls


def test_clone_uses_isolated_git_and_cleans_up_on_downstream_error(fake_transport):
    _, calls = fake_transport
    with pytest.raises(RuntimeError):
        with clone_repository("https://github.com/example/demo") as path:
            assert path.exists()
            raise RuntimeError("discovery failed")
    assert not path.parent.exists()
    command, options = calls[0]
    assert "--no-checkout" in command
    assert "credential.helper=" in command
    assert options["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert options["env"]["GIT_CONFIG_GLOBAL"] == ingestion.os.devnull


@pytest.mark.parametrize("limits, size, message", [
    (Limits(clone_seconds=-1), 0, "time limit"),
    (Limits(clone_bytes=1), 2, "storage limit"),
])
def test_clone_limits_stop_transport_and_remove_temporary_files(fake_transport, monkeypatch, limits, size, message):
    process, calls = fake_transport
    process.returncode = None
    monkeypatch.setattr(ingestion, "directory_size", lambda path: size)
    with pytest.raises(IngestionError, match=message):
        with clone_repository("https://github.com/example/demo", limits):
            pytest.fail("Clone should not succeed")
    assert process.returncode == -9
    assert not Path(calls[0][0][-1]).parent.exists()


def test_empty_or_inaccessible_repository_reports_clone_failure(fake_transport):
    process, _ = fake_transport
    process.returncode = 128
    with pytest.raises(IngestionError, match="exists and is public"):
        with clone_repository("https://github.com/example/missing"):
            pytest.fail("Clone should not succeed")
