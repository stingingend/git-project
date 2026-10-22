from sqlalchemy import select

from app.analysis import pagerank, reverse_walk, strongly_connected
from app.models import SourceFile


def test_graph_algorithms_handle_cycles_dangling_nodes_and_bounds():
    forward = {1: {2}, 2: {3}, 3: {1}, 4: set()}
    reverse = {1: {3}, 2: {1}, 3: {2}, 4: set()}
    assert strongly_connected(forward, reverse) == [[1, 2, 3]]
    scores = pagerank(forward, reverse)
    assert abs(sum(scores.values()) - 1) < 1e-8
    assert scores[1] > scores[4]
    depths, via, truncated = reverse_walk([3], reverse, 1)
    assert depths == {3: 0, 2: 1} and via == {2: 3} and truncated
    assert pagerank({}, {}) == {}
    assert strongly_connected({1: {1}}, {1: {1}}) == [[1]]


def seed(client, repository):
    with client.app.state.sessions() as session:
        for file in session.scalars(select(SourceFile).where(SourceFile.repository_id == repository)):
            session.delete(file)
        sources = {
            "a.py": "from b import work\ndef run(): return work()\n",
            "b.py": "from c import leaf\ndef work(): return leaf()\n",
            "c.py": "import a\ndef leaf():\n    if True: return 1\n",
            "tests/test_a.py": "from a import run\ndef test_run(): assert run()\n",
            "isolated.py": "x = 1\n",
        }
        session.add_all([SourceFile(repository_id=repository, path=path, source=source, line_count=3,
            content_hash=str(index) * 64) for index, (path, source) in enumerate(sources.items())])
        session.commit()
    prefix = f"/repositories/{repository}"
    assert client.post(prefix + "/parse").status_code == 200
    return prefix


def test_impact_traces_callers_and_importing_tests(client, ingested_repository):
    prefix = seed(client, ingested_repository)
    leaf = client.get(prefix + "/search", params={"q": "leaf", "kind": "function"}).json()["items"][0]["symbol"]
    response = client.post(prefix + "/impact", json={"symbol_ids": [leaf["id"]]})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["commit_sha"] == "a" * 40
    assert {row["symbol"]["name"] for row in report["symbols"]} == {"work", "run", "test_run"}
    assert {row["path"] for row in report["files"]} == {"a.py", "b.py", "tests/test_a.py"}
    assert any(row["is_test"] for row in report["files"])
    assert client.post(prefix + "/impact", json={}).status_code == 422
    assert client.post(prefix + "/impact", json={"symbol_ids": [999]}).status_code == 404
    bounded = client.post(prefix + "/impact", json={"symbol_ids": [leaf["id"]], "max_depth": 1}).json()
    assert bounded["truncated"]


def test_architecture_counts_unique_edges_cycles_and_isolation(client, ingested_repository):
    prefix = seed(client, ingested_repository)
    report = client.get(prefix + "/architecture").json()
    assert report["file_count"] == 5 and report["dependency_pairs"] == 4
    assert report["cycle_component_count"] == 1 and report["cyclic_files"] == 3
    assert report["isolated_files"] == 1
    assert {row["path"] for row in report["cycles"][0]["files"]} == {"a.py", "b.py", "c.py"}
    assert next(row for row in report["hubs"] if row["path"] == "a.py")["fan_in"] == 2
    assert next(row for row in report["hubs"] if row["path"] == "c.py")["branch_points"] == 1
    assert client.get("/repositories/999/architecture").status_code == 404
