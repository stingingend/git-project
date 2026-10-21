from datetime import datetime, timezone
import hashlib

import pytest

from app.models import Repository, RepositorySnapshot, SourceFile


@pytest.fixture
def searchable_repository(client):
    repository_id = client.post("/repositories", json={"github_url": "https://github.com/example/search"}).json()["id"]
    sources = {
        "src/actions.py": '''from __future__ import annotations
class Service:
    def run(self):
        return True
def runner():
    return True
def handle(value: str = "run", percentage: str = "100%"):
    return value
def needle_one(): pass
def needleXone(): pass
def café(): pass
''',
        "src/other.py": "def run():\n    return False\n",
        "src/broken.py": "def recovered():\n    return True\n\ndef broken(:\n",
    }
    with client.app.state.sessions() as session:
        session.get(Repository, repository_id).status = "ingested"
        session.add(RepositorySnapshot(repository_id=repository_id, commit_sha="d" * 40,
            default_branch="main", ingested_at=datetime.now(timezone.utc), file_count=len(sources),
            line_count=sum(len(source.splitlines()) for source in sources.values()), skipped_files=0))
        for path, source in sources.items():
            session.add(SourceFile(repository_id=repository_id, path=path, source=source,
                content_hash=hashlib.sha256(source.encode()).hexdigest(), line_count=len(source.splitlines())))
        session.commit()
    response = client.post(f"/repositories/{repository_id}/parse")
    assert response.status_code == 200
    return repository_id


def test_search_ranking_scopes_and_paging(client, searchable_repository):
    prefix = f"/repositories/{searchable_repository}"
    response = client.get(prefix + "/search", params={"q": " RUN ", "limit": 2})
    assert response.status_code == 200
    page = response.json()
    assert page["query"] == "RUN"
    assert page["parsed"] is True
    assert page["commit_sha"] == "d" * 40
    assert page["total"] == 4
    assert [item["symbol"]["name"] for item in page["items"]] == ["run", "run"]
    assert [item["path"] for item in page["items"]] == ["src/actions.py", "src/other.py"]
    second = client.get(prefix + "/search", params={"q": "run", "limit": 2, "offset": 2}).json()
    assert [item["symbol"]["name"] for item in second["items"]] == ["runner", "handle"]
    assert second["total"] == page["total"]
    assert client.get(prefix + "/search", params={"q": "run", "offset": 100}).json()["items"] == []


def test_kind_signature_path_and_qualified_name_filters(client, searchable_repository):
    url = f"/repositories/{searchable_repository}/search"
    methods = client.get(url, params={"q": "run", "kind": "method"}).json()
    assert methods["total"] == 1
    assert methods["items"][0]["symbol"]["qualified_name"] == "src/actions.py::Service.run"
    assert client.get(url, params={"q": "Service.run"}).json()["total"] == 1
    assert client.get(url, params={"q": "percentage: str"}).json()["items"][0]["symbol"]["name"] == "handle"
    assert client.get(url, params={"q": "src/other.py"}).json()["total"] == 1
    assert client.get(url, params={"q": "annotations", "kind": "import"}).json()["total"] == 1


@pytest.mark.parametrize("query, names", [("%", ["handle"]), ("needle_", ["needle_one"]), ("café", ["café"]), ("' OR 1=1 --", [])])
def test_literal_characters_and_unicode(client, searchable_repository, query, names):
    result = client.get(f"/repositories/{searchable_repository}/search", params={"q": query}).json()
    assert [item["symbol"]["name"] for item in result["items"]] == names
    assert result["total"] == len(names)


def test_search_does_not_leak_other_repositories_or_hide_error_flags(client, searchable_repository):
    other = client.post("/repositories", json={"github_url": "https://github.com/example/other"}).json()["id"]
    result = client.get(f"/repositories/{other}/search", params={"q": "run"}).json()
    assert result["items"] == [] and result["total"] == 0
    assert result["parsed"] is False and result["commit_sha"] is None
    recovered = client.get(f"/repositories/{searchable_repository}/search", params={"q": "recovered"}).json()
    assert recovered["items"][0]["has_parse_errors"] is True
    assert client.get("/repositories/999/search", params={"q": "run"}).status_code == 404


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}, {"q": "x" * 201}, {"q": "run", "kind": "bad"}, {"q": "run", "limit": 101}, {"q": "run", "limit": 0}, {"q": "run", "offset": -1}])
def test_search_validation(client, searchable_repository, params):
    assert client.get(f"/repositories/{searchable_repository}/search", params=params).status_code == 422
