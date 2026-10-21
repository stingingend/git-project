from app.models import SourceFile


def test_graph_groups_imports_and_preserves_direction(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    with client.app.state.sessions() as session:
        session.add_all([
            SourceFile(repository_id=ingested_repository, path="pkg/a.py", source="from .b import one, two\nimport os\nfrom . import a\n", line_count=3, content_hash="d" * 64),
            SourceFile(repository_id=ingested_repository, path="pkg/b.py", source="from . import a\n", line_count=1, content_hash="e" * 64),
            SourceFile(repository_id=ingested_repository, path="pkg/c.py", source="from . import a\n", line_count=1, content_hash="f" * 64),
        ])
        session.commit()
    client.post(prefix + "/parse")
    files = {file["path"]: file["id"] for file in client.get(prefix + "/files").json()}
    response = client.get(prefix + f"/files/{files['pkg/a.py']}/graph")
    assert response.status_code == 200
    graph = response.json()
    assert graph["ready"] and graph["commit_sha"] == "a" * 40
    assert graph["total_neighbors"] == 2
    assert graph["unresolved_imports"] == 1
    assert graph["self_imports"] == 1
    assert graph["nodes"][0] == {"id": files["pkg/a.py"], "path": "pkg/a.py"}
    assert {(e["source"], e["target"], e["count"]) for e in graph["edges"]} == {
        (files["pkg/a.py"], files["pkg/b.py"], 2),
        (files["pkg/b.py"], files["pkg/a.py"], 1),
        (files["pkg/c.py"], files["pkg/a.py"], 1),
    }


def test_graph_is_bounded_and_reports_full_neighbor_count(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    with client.app.state.sessions() as session:
        session.add(SourceFile(repository_id=ingested_repository, path="hub.py",
            source="\n".join(f"import leaf{i:02}" for i in range(15)), line_count=15, content_hash="d" * 64))
        session.add_all(SourceFile(repository_id=ingested_repository, path=f"leaf{i:02}.py",
            source="", line_count=0, content_hash="e" * 64) for i in range(15))
        session.commit()
    client.post(prefix + "/parse")
    file = next(file for file in client.get(prefix + "/files").json() if file["path"] == "hub.py")
    graph = client.get(prefix + f"/files/{file['id']}/graph").json()
    assert graph["total_neighbors"] == 15
    assert len(graph["nodes"]) == 13
    assert len(graph["edges"]) == 12
    assert [node["path"] for node in graph["nodes"]][1:] == [f"leaf{i:02}.py" for i in range(12)]
    ids = {node["id"] for node in graph["nodes"]}
    assert all(edge["source"] in ids and edge["target"] in ids for edge in graph["edges"])


def test_graph_unparsed_empty_scope_and_invalidation(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    file_id = client.get(prefix + "/files").json()[0]["id"]
    url = prefix + f"/files/{file_id}/graph"
    assert client.get(url).json()["ready"] is False
    client.post(prefix + "/parse")
    empty = client.get(url).json()
    assert empty["ready"] and empty["total_neighbors"] == 0
    assert len(empty["nodes"]) == 1 and empty["edges"] == []
    other = client.post("/repositories", json={"github_url": "https://github.com/other/graph"}).json()["id"]
    assert client.get(f"/repositories/{other}/files/{file_id}/graph").status_code == 404
    assert client.get(prefix + "/files/999/graph").status_code == 404
    from app.parsing import clear_parse_results
    with client.app.state.sessions() as session:
        clear_parse_results(session, ingested_repository)
        session.commit()
    assert client.get(url).json()["ready"] is False
