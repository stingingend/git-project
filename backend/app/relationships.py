"""Static containment and conservative language-aware dependencies; no execution."""
import ast
from collections import defaultdict
from pathlib import PurePosixPath
import posixpath

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from .models import Relationship, RelationshipSnapshot, SourceFile, Symbol
from .parser import ParsingError
from .languages import language_for_path, SCRIPT_EXTENSIONS


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if len(parts) > 1 and parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return parts


def import_modules(statement, path):
    try:
        node = ast.parse(statement).body[0]
    except (SyntaxError, ValueError, RecursionError):
        return []
    if isinstance(node, ast.Import):
        return [(item.name, [item.name]) for item in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    base = node.module or ""
    if node.level:
        package = module_name(path)
        if PurePosixPath(path).name != "__init__.py":
            package = package[:-1]
        if node.level > len(package):
            return [(statement, [])]
        prefix = package[:len(package) - node.level + 1]
        base = ".".join([*prefix, *([base] if base else [])])
    return [(f"{'.' * node.level}{node.module or ''} import {item.name}",
             ([f"{base}.{item.name}", base] if item.name != "*" else [base])
             if base and base != "__future__" else []) for item in node.names]


def script_target(path, specifier, files_by_path):
    """Resolve relative source files only; never read configs or run Node."""
    if not specifier.startswith(("./", "../")) or "\\" in specifier:
        return None, "unresolved"
    base = posixpath.normpath(posixpath.join(posixpath.dirname(path), specifier))
    if base == ".." or base.startswith("../") or base.startswith("/"):
        return None, "unresolved"
    suffix = PurePosixPath(base).suffix.lower()
    tiers = [[base]] if suffix in SCRIPT_EXTENSIONS else []
    if suffix not in SCRIPT_EXTENSIONS:
        tiers.extend([[base + extension for extension in SCRIPT_EXTENSIONS],
                      [posixpath.join(base, "index" + extension) for extension in SCRIPT_EXTENSIONS]])
    elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        substitutes = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
        tiers.append([base[:-len(suffix)] + extension for extension in substitutes[suffix]])
    for tier in tiers:
        matches = {files_by_path[candidate] for candidate in tier if candidate in files_by_path}
        if matches:
            return (next(iter(matches)), "local") if len(matches) == 1 else (None, "ambiguous")
    return None, "unresolved"


def build_relationships(session, repository_id, commit_sha, files, parsed_files):
    modules = defaultdict(set)
    for file in files:
        if language_for_path(file.path) != "Python":
            continue
        parts = module_name(file.path)
        if parts and all(part.isidentifier() for part in parts):
            modules[".".join(parts)].add(file.id)
    edges = []
    script_files = {file.path: file.id for file in files if language_for_path(file.path) in {"JavaScript", "TypeScript"}}
    for file, parents, symbols in parsed_files:
        for index, symbol in enumerate(symbols):
            parent = parents[index]
            edges.append(Relationship(repository_id=repository_id, file_id=file.id,
                kind="contains", source_symbol_id=symbols[parent].id if parent is not None else None,
                target_symbol_id=symbol.id, target_file_id=None,
                label=symbol.name, resolution="structural"))
            if len(edges) > 300_000:
                raise ParsingError("Repository exceeds the 300,000 relationship limit.")
            if symbol.symbol_type != "import":
                continue
            if language_for_path(file.path) != "Python":
                from .script_parser import script_modules
                for specifier in script_modules(symbol.signature, file.path):
                    target, resolution = script_target(file.path, specifier, script_files)
                    edges.append(Relationship(repository_id=repository_id, file_id=file.id,
                        kind="imports", source_symbol_id=symbol.id, target_symbol_id=None,
                        target_file_id=target, label=specifier, resolution=resolution))
                    if len(edges) > 300_000:
                        raise ParsingError("Repository exceeds the 300,000 relationship limit.")
                continue
            for label, candidates in import_modules(symbol.signature, file.path):
                target = None
                resolution = "unresolved"
                for candidate in candidates:
                    matches = modules.get(candidate, set())
                    if len(matches) > 1:
                        resolution = "ambiguous"
                        break
                    if matches:
                        target = next(iter(matches))
                        resolution = "local"
                        break
                edges.append(Relationship(repository_id=repository_id, file_id=file.id,
                    kind="imports", source_symbol_id=symbol.id, target_symbol_id=None,
                    target_file_id=target, label=label, resolution=resolution))
                if len(edges) > 300_000:
                    raise ParsingError("Repository exceeds the 300,000 relationship limit.")
    session.add_all(edges)
    session.add(RelationshipSnapshot(repository_id=repository_id, commit_sha=commit_sha))


def file_relationships(session, repository_id, file_id, kind, direction, limit, offset):
    file = session.scalar(select(SourceFile).where(SourceFile.id == file_id,
                                                  SourceFile.repository_id == repository_id))
    if file is None:
        return None
    snapshot = session.get(RelationshipSnapshot, repository_id)
    query = select(Relationship).where(Relationship.repository_id == repository_id)
    if direction == "incoming":
        query = query.where(Relationship.target_file_id == file_id, Relationship.kind == "imports")
    else:
        query = query.where(Relationship.file_id == file_id)
    if kind:
        query = query.where(Relationship.kind == kind)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    source = aliased(Symbol)
    target = aliased(Symbol)
    destination = aliased(SourceFile)
    origin = aliased(SourceFile)
    rows = session.execute(query.add_columns(source, target, destination, origin)
        .outerjoin(source, Relationship.source_symbol_id == source.id)
        .outerjoin(target, Relationship.target_symbol_id == target.id)
        .outerjoin(destination, Relationship.target_file_id == destination.id)
        .join(origin, Relationship.file_id == origin.id)
        .order_by(Relationship.id).limit(limit).offset(offset)).all()
    return dict(file_id=file_id, ready=snapshot is not None,
        commit_sha=snapshot.commit_sha if snapshot else None, total=total, limit=limit, offset=offset,
        items=[dict(id=edge.id, kind=edge.kind, label=edge.label, resolution=edge.resolution,
            source_name=src.name if src else origin.path,
            source_symbol_id=src.id if src else None,
            target_name=dst.name if dst else dest.path if dest else edge.label,
            target_symbol_id=dst.id if dst else None,
            file_id=origin.id, path=origin.path,
            start_line=dst.start_line if edge.kind == "contains" else src.start_line,
            target_file_id=dest.id if dest else None,
            target_path=dest.path if dest else None) for edge, src, dst, dest, origin in rows])


def dependency_graph(session, repository_id, file_id):
    """A bounded, one-hop view, aggregating repeated imports between files."""
    center = session.scalar(select(SourceFile).where(SourceFile.id == file_id,
                                                      SourceFile.repository_id == repository_id))
    if center is None:
        return None
    snapshot = session.get(RelationshipSnapshot, repository_id)
    pairs = session.execute(select(Relationship.file_id, Relationship.target_file_id, func.count())
        .where(Relationship.repository_id == repository_id, Relationship.kind == "imports",
               Relationship.resolution == "local", Relationship.target_file_id.is_not(None),
               or_(Relationship.file_id == file_id, Relationship.target_file_id == file_id))
        .group_by(Relationship.file_id, Relationship.target_file_id)).all() if snapshot else []
    neighbors = {identifier for source, target, _ in pairs for identifier in (source, target)} - {file_id}
    # Files are repository-scoped too; stable path ordering makes truncation predictable.
    files = session.scalars(select(SourceFile).where(SourceFile.repository_id == repository_id,
        SourceFile.id.in_(neighbors)).order_by(SourceFile.path, SourceFile.id).limit(12)).all() if neighbors else []
    included = {file_id, *(file.id for file in files)}
    unresolved = session.scalar(select(func.count()).select_from(Relationship).where(
        Relationship.repository_id == repository_id, Relationship.file_id == file_id,
        Relationship.kind == "imports", Relationship.resolution != "local")) if snapshot else 0
    return dict(file_id=file_id, ready=snapshot is not None,
        commit_sha=snapshot.commit_sha if snapshot else None,
        total_neighbors=len(neighbors), unresolved_imports=unresolved,
        self_imports=sum(count for source, target, count in pairs if source == target),
        nodes=[dict(id=file.id, path=file.path) for file in [center, *files]],
        edges=[dict(source=source, target=target, count=count) for source, target, count in pairs
               if source != target and source in included and target in included])
