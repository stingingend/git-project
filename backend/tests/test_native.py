"""C/C++ grammar, include graph, and mixed-index regression tests."""
import pytest
from sqlalchemy import select

from app.calls import match_calls
from app.languages import language_for_path, SCRIPT_EXTENSIONS
from app.models import IndexChanges, RepositorySnapshot, Symbol
from app.native_parser import include_target
from app.parser import ParsingError, parse_source
from app.pull_requests import analyze_pull_request
from test_ingestion import git_repository, local_clone, register
from test_incremental import commit, index, saved
from test_multilanguage import add_sources


def test_c_extracts_functions_prototypes_types_and_macros_without_pointer_variables():
    source = '''#include "app.h"
#include <stdio.h>
#define SCALE(x) ((x) * 2)
typedef int Count;
typedef int (*Callback)(int);
struct Item { int count; };
union Value { int i; float f; };
enum State { OPEN, CLOSED };
int add(int x);
int (*callback)(int);
int *make(int x) { return 0; }
int (*factory(void))(int) { return 0; }
int add(int x) { return x + 1; }
int main(void) { return add(1); }
'''
    result = parse_source(source, "src/app.c")
    assert not result.has_parse_errors
    kinds = {(symbol.name, symbol.symbol_type) for symbol in result.symbols}
    assert {("SCALE", "macro"), ("Count", "type"), ("Callback", "type"), ("Item", "struct"),
            ("Value", "union"), ("State", "enum"), ("add", "declaration"), ("add", "function"),
            ("make", "function"), ("factory", "function")} <= kinds
    assert not any(symbol.name == "callback" for symbol in result.symbols)
    assert result.symbols[0].start_line == result.symbols[0].end_line == 1
    call, target, resolution = next(match_calls(result, "C"))
    assert call.expression == "add" and resolution == "candidate"
    assert result.symbols[target].symbol_type == "function"


@pytest.mark.parametrize("extension", ["cpp", "cc", "cxx", "c++", "hpp", "hh", "hxx", "h++", "ipp", "tpp", "inl", "C"])
def test_cpp_scopes_templates_constructors_operators_and_lambdas(extension):
    source = '''namespace app {
template<class T> struct Box {
 Box() {}
 ~Box() {}
 T get() { return T{}; }
 T run() { return get(); }
 operator bool() const { return true; }
 Box operator+(Box value) { return value; }
 T declared();
};
using ID = unsigned;
int helper(int x) { return x; }
int overloaded(int x) {return x;}
int overloaded(double x) {return 1;}
int call() { return overloaded(1); }
auto twice = [](int x) { return helper(x); };
}
'''
    result = parse_source(source, f"src/box.{extension}")
    assert not result.has_parse_errors
    kinds = {(symbol.name, symbol.symbol_type) for symbol in result.symbols}
    assert {("app", "namespace"), ("Box", "struct"), ("Box", "method"), ("~Box", "method"),
            ("operator bool", "method"), ("operator+", "method"), ("declared", "declaration"),
            ("ID", "type"), ("twice", "function")} <= kinds
    box = next(symbol for symbol in result.symbols if symbol.symbol_type == "struct")
    assert box.start_line == 2 and box.signature.startswith("template<class T>")
    calls = list(match_calls(result, "C++"))
    assert next(row for row in calls if row[0].expression == "overloaded")[2] == "ambiguous"
    assert next(row for row in calls if row[0].expression == "get")[2] == "candidate"
    assert next(row for row in calls if row[0].expression == "helper")[2] == "candidate"
    for symbol, parent in zip(result.symbols, result.parents):
        assert symbol.parent_qualified_name == (result.symbols[parent].qualified_name if parent is not None else None)


def test_header_language_inference_and_uppercase_c():
    assert language_for_path("a.h", "int sum(int, int);\n") == "C"
    assert language_for_path("a.h", '/* class Foo {}; */\nconst char *s = "namespace app {}";') == "C"
    assert language_for_path("a.h", "class Foo {};") == "C++"
    assert language_for_path("a.h", 'extern "C" { int run(void); }') == "C++"
    assert language_for_path("a.h", "namespace app { class Foo { public: Foo() {} }; }\n") == "C++"
    assert language_for_path("a.C") == "C++"
    assert language_for_path("a.c") == "C"
    assert not set(SCRIPT_EXTENSIONS) & {".c", ".h", ".cpp", ".hpp"}
    result = parse_source("namespace app { class Foo {}; }", "a.h")
    assert not result.has_parse_errors and result.symbols[0].name == "app"


def test_native_source_never_executes_and_limits_hold(tmp_path):
    destination = tmp_path / "must-not-exist"
    source = '#include <stdlib.h>\nint main(void) { system("do-not-run"); return 0; }\n'
    result = parse_source(source, "untrusted.c")
    assert not result.has_parse_errors and not destination.exists()
    assert result.calls[0].expression == "system"
    broken = parse_source("int valid(void) {return 1;}\nint broken( {", "broken.cpp")
    assert broken.has_parse_errors and any(symbol.name == "valid" for symbol in broken.symbols)
    assert parse_source("", "empty.h").symbols == []
    with pytest.raises(ParsingError, match="symbol limit"):
        parse_source("int a(){} int b(){}", "x.c", max_symbols=1)
    with pytest.raises(ParsingError, match="call limit"):
        parse_source("int run(){ a(); b(); }", "x.cpp", max_calls=1)


def test_include_resolution_is_bounded_and_ambiguous_roots_are_not_guessed():
    paths = {"src/local.h": 1, "include/project/api.hpp": 2, "common.h": 3, "include/common.h": 4}
    assert include_target("src/main.c", '#include "local.h"', paths) == ("local.h", 1, "local")
    assert include_target("src/main.cpp", '#include <project/api.hpp>', paths) == ("project/api.hpp", 2, "local")
    assert include_target("src/main.c", '#include "common.h"', paths) == ("common.h", None, "ambiguous")
    for statement in ['#include <stdio.h>', '#include "../../outside.h"', '#include "/etc/passwd"', '#include HEADER_MACRO']:
        assert include_target("src/main.c", statement, paths)[2] == "unresolved"


@pytest.fixture
def native(client, git_repository, local_clone):
    add_sources(git_repository, {
        "src/app.c": '#include "api.h"\n#include <stdio.h>\nint helper(int x) {return x + 1;}\nint run(void) {return helper(1);}\n',
        "src/api.h": '#pragma once\nint helper(int x);\nstruct Record { int value; };\n',
        "include/box.h": 'namespace demo { template<class T> class Box { public: T get() {return T{};} }; }\n',
        "src/main.cpp": '#include <box.h>\nnamespace demo { int calculate(int x) { if(x) return x; return 0; } }\n',
        "src/legacy.C": 'class Legacy { public: int run() {return 1;} };\n',
        "src/bridge.js": 'import "./app.c";\nexport const run = () => 1;\n',
        "build/generated.cpp": 'int omitted() {}\n',
    })
    repo = register(client)
    prefix = f"/repositories/{repo}"
    index(client, prefix)
    return repo, prefix, git_repository


def test_native_pipeline_and_script_isolation(client, native):
    repo, prefix, _ = native
    files = {file["path"]: file for file in client.get(prefix + "/files").json()}
    assert files["src/api.h"]["language"] == "C"
    assert files["include/box.h"]["language"] == "C++"
    assert files["src/legacy.C"]["language"] == "C++"
    assert "build/generated.cpp" not in files
    graph = client.get(prefix + f"/files/{files['src/app.c']['id']}/graph").json()
    assert {node["path"] for node in graph["nodes"]} == {"src/app.c", "src/api.h"}
    assert graph["unresolved_imports"] == 1
    cpp_graph = client.get(prefix + f"/files/{files['src/main.cpp']['id']}/graph").json()
    assert "include/box.h" in {node["path"] for node in cpp_graph["nodes"]}
    js_graph = client.get(prefix + f"/files/{files['src/bridge.js']['id']}/graph").json()
    assert js_graph["total_neighbors"] == 0 and js_graph["unresolved_imports"] == 1
    calls = client.get(prefix + f"/files/{files['src/app.c']['id']}/calls").json()["items"]
    assert calls[0]["resolution"] == "candidate" and calls[0]["target"]["name"] == "helper"
    assert client.get(prefix + "/search?q=Record&kind=struct").json()["total"] == 1
    assert client.get(prefix + "/search?q=helper&kind=declaration").json()["total"] == 1
    assert client.get(prefix + "/overview").json()["languages"] == {"Python": 3, "JavaScript": 1, "C": 2, "C++": 3}


def test_native_semantic_architecture_pr_and_incremental_reuse(client, native, monkeypatch):
    repo, prefix, root = native
    before = saved(client)
    index(client, prefix)
    assert saved(client) == before
    with client.app.state.sessions() as session:
        changes = session.get(IndexChanges, repo)
        assert changes.parsed_files == 0 and changes.reused_files == len(before)
    monkeypatch.setattr("app.semantic.encode", lambda texts: [[1.0, *([0.0] * 255)] for _ in texts])
    assert client.post(prefix + "/semantic").status_code == 200
    hits = client.get(prefix + "/semantic/search?q=Record&limit=20").json()["items"]
    assert any(hit["path"].endswith((".c", ".cpp", ".h")) for hit in hits)
    architecture = client.get(prefix + "/architecture").json()
    assert architecture["parse_error_files"] == 0
    assert all(row["branch_points"] is not None for row in architecture["hubs"])
    with client.app.state.sessions() as session:
        sha = session.get(RepositorySnapshot, repo).commit_sha
        report = analyze_pull_request(session, repo, dict(base_sha=sha, head_sha="b" * 40, files=[dict(
            filename="src/app.c", status="modified", additions=0, deletions=1, patch="@@ -3,1 +3,0 @@\n-int helper(int x) {return x + 1;}")]))
        assert report["files"][0]["supported"] and report["changed_symbol_count"] > 0
    (root / "src/api.h").unlink()
    commit(root, "remove header")
    index(client, prefix)
    files = {file["path"]: file for file in client.get(prefix + "/files").json()}
    graph = client.get(prefix + f"/files/{files['src/app.c']['id']}/graph").json()
    assert graph["unresolved_imports"] == 2
    assert saved(client)["src/app.c"] == before["src/app.c"]
