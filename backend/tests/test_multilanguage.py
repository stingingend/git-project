"""Mixed-language source is indexed without installing or running project code."""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import FileIndexState, IndexChanges, SourceFile, Symbol
from app.parser import ParsingError, parse_source
from app.pull_requests import analyze_pull_request
from test_ingestion import git_repository, local_clone, register
from test_incremental import commit, index, saved


@pytest.mark.parametrize("extension", ["js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts"])
def test_script_grammars_extract_definitions_calls_and_unicode(extension):
    source = '''import { value } from "./lib";
export function café(x) { return x; }
const twice = (x) => café(café(x));
export class Service {
  run() { return this.go(); }
  go() { return twice(1); }
  arrow = (x) => café(x);
}
new Service();
'''
    result = parse_source(source, f"src/main.{extension}")
    assert not result.has_parse_errors
    symbols = {symbol.name: symbol for symbol in result.symbols}
    assert symbols["café"].symbol_type == "function"
    assert symbols["twice"].symbol_type == "function"
    assert symbols["Service"].symbol_type == "class"
    assert symbols["run"].parent_qualified_name == f"src/main.{extension}::Service"
    assert symbols["arrow"].symbol_type == "method"
    assert symbols["café"].start_line == 2
    assert {call.expression for call in result.calls} >= {"café", "twice", "this.go", "Service"}
    for parent, child in zip(result.parents, result.symbols):
        assert child.parent_qualified_name == (result.symbols[parent].qualified_name if parent is not None else None)


def test_typescript_tsx_and_anonymous_exports():
    result = parse_source('''export interface Props { label: string }
export type ID = string;
export const View = ({label}: Props) => <button>{label}</button>;
export default function() { return <View label="Hi"/>; }
''', "src/page.tsx")
    assert not result.has_parse_errors
    assert [(s.name, s.symbol_type) for s in result.symbols] == [
        ("Props", "interface"), ("ID", "type"), ("View", "function"), ("default", "function")]
    assert parse_source("const C = class { run() {} };", "x.js").symbols[0].name == "C"
    assert parse_source("export default () => 1", "x.js").symbols[0].name == "default"


def test_script_limits_errors_and_source_only_parsing(tmp_path):
    destination = tmp_path / "must-not-exist"
    source = f'const fs = require("fs"); fs.writeFileSync({str(destination)!r}, "bad"); function good() {{}} function broken( {{'
    result = parse_source(source, "untrusted.js")
    assert result.has_parse_errors and any(s.name == "good" for s in result.symbols)
    assert not destination.exists()
    assert parse_source("", "empty.ts").symbols == []
    with pytest.raises(ParsingError, match="symbol limit"):
        parse_source("const x=()=>1; const y=()=>2", "x.ts", max_symbols=1)
    with pytest.raises(ParsingError, match="call limit"):
        parse_source("a(); b();", "x.js", max_calls=1)
    with pytest.raises(ParsingError, match="Unsupported"):
        parse_source("hello", "x.rs")


def add_sources(root, sources):
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    commit(root, "add script fixtures")


@pytest.fixture
def mixed(client, git_repository, local_clone):
    add_sources(git_repository, {
        "src/main.ts": '''import { helper } from './lib.js';
import React from 'react';
export interface Props { name: string }
export type ID = string;
function local() { return 1; }
export class Service {
 run() { return this.go(); }
 go() { return local(); }
}
export const start = () => helper();
''',
        "src/lib.ts": "export function helper() { return 2; }\n",
        "src/ui.tsx": "import { start } from './main';\nexport const View = () => <div/>;\n",
        "src/bridge.cjs": "const lib = require('./lib.js');\nmodule.exports = lib;\n",
        "src/pkg/index.js": "export { helper } from '../lib.js';\n",
        "src/use.mjs": "import './pkg';\nimport('./lib.js');\nrequire(variable);\n",
        "src/lib.py": "def helper(): return 4\n",
        "src/python.py": "from lib import helper\nhelper()\n",
        "node_modules/dependency/index.js": "throw new Error('not included');\n",
        ".next/bundle.js": "throw new Error('not included');\n",
        "src/notes.txt": "not source",
    })
    repo = register(client)
    prefix = f"/repositories/{repo}"
    index(client, prefix)
    return repo, prefix, git_repository


def test_mixed_pipeline_languages_graphs_calls_and_search(client, mixed):
    repo, prefix, _ = mixed
    files = {file["path"]: file for file in client.get(prefix + "/files").json()}
    assert files["src/ui.tsx"]["language"] == "TypeScript"
    assert files["src/bridge.cjs"]["language"] == "JavaScript"
    assert not any(path.startswith(("node_modules/", ".next/")) for path in files)
    overview = client.get(prefix + "/overview").json()
    assert overview["languages"] == {"JavaScript": 3, "TypeScript": 3, "Python": 5}
    main = files["src/main.ts"]["id"]
    graph = client.get(prefix + f"/files/{main}/graph").json()
    assert any(node["path"] == "src/lib.ts" for node in graph["nodes"])
    assert graph["unresolved_imports"] == 1  # external React
    calls = client.get(prefix + f"/files/{main}/calls").json()["items"]
    assert next(c for c in calls if c["expression"] == "this.go")["target"]["name"] == "go"
    assert next(c for c in calls if c["expression"] == "local")["resolution"] == "candidate"
    assert next(c for c in calls if c["expression"] == "helper")["resolution"] == "unresolved"
    interfaces = client.get(prefix + "/search?q=Props&kind=interface").json()
    assert interfaces["total"] == 1
    assert client.get(prefix + "/search?q=ID&kind=type").json()["total"] == 1
    for origin, destination in [("src/bridge.cjs", "src/lib.ts"), ("src/use.mjs", "src/pkg/index.js"), ("src/pkg/index.js", "src/lib.ts"), ("src/python.py", "src/lib.py")]:
        graph = client.get(prefix + f"/files/{files[origin]['id']}/graph").json()
        assert destination in {node["path"] for node in graph["nodes"]}
    caps = client.get("/capabilities").json()
    assert caps["languages"] == ["Python", "JavaScript", "TypeScript", "C", "C++"]


def test_script_incremental_updates_reuse_and_invalidate_graph_targets(client, mixed):
    repo, prefix, root = mixed
    before = saved(client)
    index(client, prefix)
    assert saved(client) == before
    with client.app.state.sessions() as session:
        changes = session.get(IndexChanges, repo)
        assert changes.parsed_files == 0 and changes.reused_files == len(before)
    # Removing a JS/TS dependency rebuilds global links even when importers reuse syntax.
    (root / "src/lib.ts").unlink()
    commit(root, "remove lib")
    index(client, prefix)
    files = {f["path"]: f for f in client.get(prefix + "/files").json()}
    graph = client.get(prefix + f"/files/{files['src/main.ts']['id']}/graph").json()
    assert graph["unresolved_imports"] == 2
    assert saved(client)["src/main.ts"] == before["src/main.ts"]
    assert "src/lib.ts" not in saved(client)


def test_mixed_semantic_architecture_and_pr_mapping(client, mixed, monkeypatch):
    repo, prefix, _ = mixed
    monkeypatch.setattr("app.semantic.encode", lambda texts: [[1.0, *([0.0] * 255)] for _ in texts])
    response = client.post(prefix + "/semantic")
    assert response.status_code == 200, response.text
    found = client.get(prefix + "/semantic/search?q=Props&limit=20").json()
    assert any(hit["path"].endswith((".ts", ".tsx", ".js")) for hit in found["items"])
    architecture = client.get(prefix + "/architecture")
    assert architecture.status_code == 200, architecture.text
    assert all(row["branch_points"] is not None for row in architecture.json()["hubs"])
    with client.app.state.sessions() as session:
        from app.models import RepositorySnapshot
        sha = session.get(RepositorySnapshot, repo).commit_sha
        report = analyze_pull_request(session, repo, dict(base_sha=sha, head_sha="b" * 40, files=[dict(
            filename="src/main.ts", status="modified", additions=1, deletions=1,
            patch="@@ -5,1 +5,1 @@\n-function local() { return 1; }\n+function local() { return 2; }")]))
        assert report["files"][0]["supported"]
        changed = {symbol.name for symbol in session.scalars(select(Symbol).where(Symbol.id.in_(report["changed_symbol_ids"])))}
        assert "local" in changed


def test_module_resolution_stays_conservative():
    from app.relationships import script_target
    paths = {"src/lib.js": 1, "src/lib.ts": 2, "src/pkg/index.ts": 3, "src/python.py": 4,
             "src/config.client.ts": 5, "src/case.JS": 6}
    assert script_target("src/a.ts", "./lib", paths) == (None, "ambiguous")
    assert script_target("src/a.ts", "./lib.js", paths) == (1, "local")
    assert script_target("src/a.ts", "./pkg", paths) == (3, "local")
    assert script_target("src/a.ts", "./config.client", paths) == (5, "local")
    assert script_target("src/a.ts", "./case.JS", paths) == (6, "local")
    assert script_target("src/a.ts", "./python.py", paths) == (None, "unresolved")
    for specifier in ["@/lib", "react", "https://example.com/x.js", "../../outside", "./missing"]:
        assert script_target("src/a.ts", specifier, paths) == (None, "unresolved")
