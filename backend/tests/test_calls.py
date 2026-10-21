import pytest
from sqlalchemy import select

from app.calls import match_calls
from app.models import CallSite, SourceFile
from app.parser import ParsingError, parse_python


def matches(source):
    result = parse_python(source, "sample.py")
    return result, list(match_calls(result))


def test_extract_call_expressions_ranges_and_recovered_syntax():
    result = parse_python("def run():\n    outer(inner(), obj.go())\n    factories[0]()\ndef broken(:\n", "sample.py")
    assert result.has_parse_errors
    assert [(c.expression, c.call_type) for c in result.calls] == [
        ("outer", "direct"), ("inner", "direct"), ("obj.go", "attribute"), ("factories[0]", "dynamic")]
    assert result.calls[0].start_line == 2 and result.calls[0].column == 5
    assert result.calls[0].end_line == 2
    assert all(call.caller_index == 0 for call in result.calls)
    with pytest.raises(ParsingError, match="call limit"):
        parse_python("one(); two()", "sample.py", max_calls=1)


def test_nearest_scope_recursion_and_class_namespace_rules():
    result, calls = matches("""def helper(): pass
class Service:
    def helper(self): pass
    def run(self):
        helper()
        self.helper()
def outer():
    def helper(): pass
    helper()
    outer()
Service()
""")
    targets = [result.symbols[target].qualified_name if target is not None else None for _, target, _ in calls]
    assert targets == ["sample.py::helper", None, "sample.py::outer.helper", "sample.py::outer", "sample.py::Service"]
    assert calls[1][2] == "unresolved"


def test_long_dynamic_labels_are_bounded_and_unicode_names_match():
    result, calls = matches("def café(): pass\ncafé()\n" + "factory()" + "()" * 200)
    assert calls[0][2] == "candidate"
    assert result.symbols[calls[0][1]].name == "café"
    assert all(len(call.expression) <= 300 for call in result.calls)
    assert len(result.calls) == 202


def test_repeated_definitions_are_ambiguous_and_exact_parent_identity_is_preserved():
    result, calls = matches("""def repeat(): pass
def repeat(): pass
repeat()
def outer():
    def leaf(): pass
    leaf()
def outer():
    def leaf(): pass
    leaf()
""")
    assert calls[0][1:] == (None, "ambiguous")
    assert calls[1][1] != calls[2][1]
    assert result.parents[calls[1][1]] == calls[1][0].caller_index
    assert result.parents[calls[2][1]] == calls[2][0].caller_index


@pytest.fixture
def indexed_calls(client, ingested_repository):
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.repository_id == ingested_repository,
                                                       SourceFile.path == "app.py"))
        file.source = "def helper(): return 1\ndef run():\n    helper(); print('hello'); obj.go()\nrun()\n"
        file_id = file.id
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    assert client.post(prefix + "/parse").status_code == 200
    return prefix, file_id


def test_call_pages_summary_filter_scope_and_replacement(client, indexed_calls):
    prefix, file_id = indexed_calls
    url = prefix + f"/files/{file_id}/calls"
    response = client.get(url)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["ready"] and page["commit_sha"] == "a" * 40
    assert page["summary"] == {"total": 4, "candidates": 2, "ambiguous": 0, "unresolved": 2}
    assert page["items"][0]["caller"]["name"] == "run"
    assert page["items"][0]["target"]["name"] == "helper"
    assert page["items"][-1]["caller"] is None
    assert client.get(url, params={"limit": 1, "offset": 2}).json()["items"] == page["items"][2:3]
    filtered = client.get(url, params={"resolution": "candidate"}).json()
    assert filtered["total"] == 2 and filtered["summary"] == page["summary"]
    assert all(call["target"] for call in filtered["items"])
    assert client.post(prefix + "/parse").status_code == 200
    assert client.get(url).json()["total"] == 4
    other = client.post("/repositories", json={"github_url": "https://github.com/example/calls"}).json()["id"]
    assert client.get(f"/repositories/{other}/files/{file_id}/calls").status_code == 404
    assert client.get(prefix + "/files/999/calls").status_code == 404
    for params in ({"resolution": "resolved"}, {"limit": 101}, {"offset": -1}):
        assert client.get(url, params=params).status_code == 422


def test_call_limit_preserves_previous_index_and_clear_invalidates(client, indexed_calls, monkeypatch):
    from app.parsing import clear_parse_results
    prefix, file_id = indexed_calls
    url = prefix + f"/files/{file_id}/calls"
    before = client.get(url).json()
    monkeypatch.setattr("app.parsing.MAX_CALLS", 1)
    assert client.post(prefix + "/parse").status_code == 422
    assert client.get(url).json() == before
    with client.app.state.sessions() as session:
        clear_parse_results(session, int(prefix.split("/")[-1]))
        session.commit()
        assert session.scalars(select(CallSite)).all() == []
    assert client.get(url).json()["ready"] is False


def test_call_write_failure_rolls_back_symbols_and_calls(client, indexed_calls, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    prefix, file_id = indexed_calls
    url = prefix + f"/files/{file_id}/calls"
    before = client.get(url).json()
    symbols = client.get(prefix + "/symbols").json()
    monkeypatch.setattr("app.parsing.INDEX_FORMAT_VERSION", "upgrade")
    engine = client.app.state.sessions.kw["bind"]
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TRIGGER reject_calls BEFORE INSERT ON call_sites "
                                  "BEGIN SELECT RAISE(ABORT, 'simulated call failure'); END")
    try:
        with pytest.raises(IntegrityError):
            client.post(prefix + "/parse")
        assert client.get(url).json() == before
        assert client.get(prefix + "/symbols").json() == symbols
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER reject_calls")


def test_old_index_not_ready_and_empty_parsed_file_distinct(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    file_id = client.get(prefix + "/files").json()[0]["id"]
    url = prefix + f"/files/{file_id}/calls"
    assert client.get(url).json()["ready"] is False
    client.post(prefix + "/parse")
    assert client.get(url).json()["ready"] is True
    assert client.get(url).json()["total"] == 0
