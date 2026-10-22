"""Approximate lexical, import, and receiver matches; never runtime call resolution."""
from collections import defaultdict
import ast
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from .models import CallSite, CallSnapshot, FileParse, SourceFile, Symbol, CallOrigin
from .relationships import module_name
from .languages import language_for_path


def match_calls(result, language="Python"):
    definitions = defaultdict(list)
    for index, symbol in enumerate(result.symbols):
        if symbol.symbol_type in {"function", "class", "method"}:
            definitions[(result.parents[index], symbol.name)].append(index)
    cache = {}
    for call in result.calls:
        key = (call.caller_index, call.direct_name)
        if key not in cache:
            target, resolution = None, "unresolved"
            scope = call.caller_index
            if call.direct_name is not None:
                while True:
                    # Function bodies do not close over a class namespace.
                    is_class = scope is not None and result.symbols[scope].symbol_type == "class"
                    if language in {"C", "C++"} or not is_class or scope == call.caller_index:
                        matches = definitions.get((scope, call.direct_name), [])
                        if matches:
                            target = matches[0] if len(matches) == 1 else None
                            resolution = "candidate" if target is not None else "ambiguous"
                            break
                    if scope is None:
                        break
                    scope = result.parents[scope]
            cache[key] = target, resolution
        yield call, *cache[key]


def build_calls(session, repository_id, parsed_files):
    created = []
    for file, result, symbols in parsed_files:
        for call, target, resolution in match_calls(result, file.language):
            created.append(CallSite(repository_id=repository_id, file_id=file.id,
                caller_symbol_id=symbols[call.caller_index].id if call.caller_index is not None else None,
                target_symbol_id=symbols[target].id if target is not None else None,
                expression=call.expression, call_type=call.call_type, resolution=resolution,
                start_line=call.start_line, end_line=call.end_line, column=call.column))
    session.add_all(created)
    session.flush()
    session.add_all([CallOrigin(call_id=call.id, target_symbol_id=call.target_symbol_id,
                               resolution=call.resolution) for call in created])


def resolve_repository_calls(session, repository_id, files, structure):
    """Suggest explicit imported functions and self/cls methods; never infer types."""
    modules = defaultdict(list)
    definitions = defaultdict(list)
    bindings = defaultdict(lambda: defaultdict(list))
    parents_by_id = {}
    for file in files:
        if language_for_path(file.path) == "Python":
            modules[".".join(module_name(file.path))].append(file.id)
    languages = {file.id: file.language for file in files}
    for file, parents, symbols in structure:
        for index, symbol in enumerate(symbols):
            parent = symbols[parents[index]] if parents[index] is not None else None
            parents_by_id[symbol.id] = parent
            if symbol.symbol_type in {"function", "class", "method"}:
                definitions[(file.id, parent.id if parent else None, symbol.name)].append(symbol)
            if symbol.symbol_type != "import" or parent is not None or languages[file.id] != "Python":
                continue
            try:
                node = ast.parse(symbol.signature).body[0]
            except (SyntaxError, ValueError, RecursionError):
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Unaliased dotted imports bind their full expression prefix.
                    bindings[file.id][alias.asname or alias.name].append((alias.name, None))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = module_name(file.path)
                    if PurePosixPath(file.path).name != "__init__.py":
                        package = package[:-1]
                    if node.level > len(package):
                        continue
                    base = ".".join([*package[:len(package) - node.level + 1], *([base] if base else [])])
                for alias in node.names:
                    if alias.name != "*":
                        bindings[file.id][alias.asname or alias.name].append((base, alias.name))
    calls = session.scalars(select(CallSite).where(CallSite.repository_id == repository_id))
    for call in calls:
        if call.resolution != "unresolved" or call.call_type == "dynamic":
            continue
        matches = []
        parts = call.expression.split(".")
        receivers = ({"self", "cls"} if languages[call.file_id] == "Python" else
                     {"this"} if languages[call.file_id] in {"JavaScript", "TypeScript"} else set())
        if len(parts) == 2 and parts[0] in receivers:
            parent = parents_by_id.get(call.caller_symbol_id)
            if parent is not None and parent.symbol_type == "class":
                matches.extend(definitions.get((call.file_id, parent.id, parts[1]), []))
        for prefix, targets in bindings[call.file_id].items():
            for module, imported in targets:
                name = None
                if imported and call.expression == prefix:
                    name = imported
                elif not imported and call.expression.startswith(prefix + "."):
                    suffix = call.expression[len(prefix) + 1:]
                    if suffix.isidentifier():
                        name = suffix
                if name:
                    for file_id in modules.get(module, []):
                        matches.extend(definitions.get((file_id, None, name), []))
        unique = {symbol.id: symbol for symbol in matches}
        if len(unique) == 1:
            call.target_symbol_id = next(iter(unique))
            call.resolution = "candidate"
        elif len(unique) > 1:
            call.resolution = "ambiguous"


def file_calls(session, repository_id, file_id, resolution, limit, offset):
    file = session.scalar(select(SourceFile).where(SourceFile.id == file_id,
                                                  SourceFile.repository_id == repository_id))
    if file is None:
        return None
    snapshot = session.get(CallSnapshot, repository_id)
    parsed = session.get(FileParse, file_id)
    base = select(CallSite).where(CallSite.repository_id == repository_id, CallSite.file_id == file_id)
    counts = dict(session.execute(select(CallSite.resolution, func.count()).where(
        CallSite.repository_id == repository_id, CallSite.file_id == file_id)
        .group_by(CallSite.resolution)).all())
    query = base.where(CallSite.resolution == resolution) if resolution else base
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    caller, target = aliased(Symbol), aliased(Symbol)
    rows = session.execute(query.add_columns(caller, target)
        .outerjoin(caller, CallSite.caller_symbol_id == caller.id)
        .outerjoin(target, CallSite.target_symbol_id == target.id)
        .order_by(CallSite.start_line, CallSite.column, CallSite.id).limit(limit).offset(offset)).all()
    return dict(file_id=file_id, ready=snapshot is not None,
        commit_sha=snapshot.commit_sha if snapshot else None,
        has_parse_errors=parsed.has_parse_errors if parsed else False,
        summary=dict(total=sum(counts.values()), candidates=counts.get("candidate", 0),
                     ambiguous=counts.get("ambiguous", 0), unresolved=counts.get("unresolved", 0)),
        total=total, limit=limit, offset=offset,
        items=[dict(id=call.id, expression=call.expression, call_type=call.call_type,
            start_line=call.start_line, end_line=call.end_line, column=call.column,
            resolution=call.resolution, caller=source, target=destination)
            for call, source, destination in rows])
