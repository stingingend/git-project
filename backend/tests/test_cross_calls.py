from sqlalchemy import select

from app.models import SourceFile
from test_incremental import commit, index, saved
from test_ingestion import git_repository, local_clone, register


def test_explicit_import_aliases_and_receiver_methods(client, ingested_repository):
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.path == "app.py"))
        file.source = "from helpers import work as go\nimport helpers as h\nclass A:\n    def run(self):\n        go(); h.work(); self.helper()\n    def helper(self): pass\n"
        file_id = file.id
        session.add(SourceFile(repository_id=ingested_repository, path="helpers.py", content_hash="d" * 64,
            line_count=1, source="def work(): return 1\n"))
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    assert client.post(prefix + "/parse").status_code == 200
    calls = client.get(prefix + f"/files/{file_id}/calls").json()["items"]
    assert [call["target"]["name"] for call in calls] == ["work", "work", "helper"]
    assert all(call["resolution"] == "candidate" for call in calls)


def test_unchanged_imported_calls_relink_after_target_changes(client, local_clone, git_repository):
    (git_repository / "src/app.py").write_text("from helper import work\ndef run(): return work()\n")
    (git_repository / "src/helper.py").write_text("def work(): return 1\n")
    commit(git_repository, "imported call")
    repo = register(client)
    prefix = f"/repositories/{repo}"
    index(client, prefix)
    before = saved(client)["src/app.py"]
    url = prefix + f"/files/{before[0]}/calls"
    assert client.get(url).json()["items"][0]["target"]["name"] == "work"
    (git_repository / "src/helper.py").write_text("def work(): return 2\ndef work(): return 3\n")
    commit(git_repository, "ambiguous target")
    index(client, prefix)
    assert client.get(url).json()["items"][0]["resolution"] == "ambiguous"
    (git_repository / "src/helper.py").unlink()
    commit(git_repository, "remove target")
    index(client, prefix)
    assert client.get(url).json()["items"][0]["resolution"] == "unresolved"
    assert saved(client)["src/app.py"] == before
