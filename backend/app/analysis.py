"""Bounded static impact and architecture metrics over a published snapshot."""
from collections import defaultdict, deque

from sqlalchemy import select

from .models import CallSite, ParseSnapshot, Relationship, SourceFile, Symbol
from .languages import language_parser
from .schemas import SymbolRead
from .semantic import require_index


def file_graph(session, repository_id):
    files = {file.id: file for file in session.scalars(select(SourceFile).where(SourceFile.repository_id == repository_id))}
    forward = {file_id: set() for file_id in files}
    reverse = {file_id: set() for file_id in files}
    unresolved = 0
    for edge in session.scalars(select(Relationship).where(Relationship.repository_id == repository_id,
                                                          Relationship.kind == "imports")):
        if edge.resolution == "local" and edge.target_file_id in files:
            forward[edge.file_id].add(edge.target_file_id)
            reverse[edge.target_file_id].add(edge.file_id)
        else:
            unresolved += 1
    return files, forward, reverse, unresolved


def reverse_walk(seeds, reverse, max_depth, max_nodes=5000):
    ordered = sorted(set(seeds))
    depths = {node: 0 for node in ordered[:max_nodes]}
    via = {}
    queue = deque(depths)
    truncated = len(ordered) > max_nodes
    while queue:
        node = queue.popleft()
        for neighbor in sorted(reverse.get(node, ())):
            if neighbor in depths:
                continue
            if depths[node] >= max_depth or len(depths) >= max_nodes:
                truncated = True
                continue
            depths[neighbor] = depths[node] + 1
            via[neighbor] = node
            queue.append(neighbor)
    return depths, via, truncated


def impact(session, repository_id, file_ids=(), symbol_ids=(), max_depth=6, limit=100, seed_all_file_symbols=True):
    _, snapshot = require_index(session, repository_id)
    files, _, reverse_files, unresolved_imports = file_graph(session, repository_id)
    symbols = {symbol.id: symbol for symbol in session.scalars(select(Symbol).where(Symbol.file_id.in_(files)))}
    if not set(file_ids) <= files.keys() or not set(symbol_ids) <= symbols.keys():
        raise LookupError("A selected file or symbol is not in this repository.")
    seed_files = set(file_ids) | {symbols[symbol_id].file_id for symbol_id in symbol_ids}
    seed_symbols = set(symbol_ids) | {symbol.id for symbol in symbols.values() if seed_all_file_symbols and symbol.file_id in file_ids}
    # A changed class/definition can affect its nested definitions.
    children = defaultdict(set)
    for edge in session.scalars(select(Relationship).where(Relationship.repository_id == repository_id,
                                                          Relationship.kind == "contains")):
        if edge.source_symbol_id is not None:
            children[edge.source_symbol_id].add(edge.target_symbol_id)
    pending = list(seed_symbols)
    while pending:
        for child in children[pending.pop()]:
            if child not in seed_symbols:
                seed_symbols.add(child)
                pending.append(child)
    reverse_calls = defaultdict(set)
    unresolved_calls = 0
    for call in session.scalars(select(CallSite).where(CallSite.repository_id == repository_id)):
        if call.resolution == "candidate" and call.target_symbol_id in symbols and call.caller_symbol_id in symbols:
            reverse_calls[call.target_symbol_id].add(call.caller_symbol_id)
        elif call.resolution != "candidate":
            unresolved_calls += 1
    symbol_depth, symbol_via, symbols_truncated = reverse_walk(seed_symbols, reverse_calls, max_depth)
    file_depth, file_via, files_truncated = reverse_walk(seed_files, reverse_files, max_depth)
    for symbol_id, depth in symbol_depth.items():
        file_id = symbols[symbol_id].file_id
        if file_id not in seed_files:
            file_depth[file_id] = min(file_depth.get(file_id, depth), depth)
    affected_files = sorted((file_id for file_id in file_depth if file_id not in seed_files),
                            key=lambda file_id: (file_depth[file_id], files[file_id].path))
    affected_symbols = sorted((symbol_id for symbol_id in symbol_depth if symbol_id not in seed_symbols),
                              key=lambda symbol_id: (symbol_depth[symbol_id], files[symbols[symbol_id].file_id].path,
                                                     symbols[symbol_id].start_line, symbol_id))
    count = len(affected_files)
    return dict(repository_id=repository_id, commit_sha=snapshot.commit_sha,
        seed_file_ids=sorted(seed_files), seed_symbol_ids=sorted(seed_symbols)[:limit],
        affected_file_count=count, affected_symbol_count=len(affected_symbols),
        scope="broad" if count >= 20 else "medium" if count >= 5 else "small",
        scope_rule="small: <5 dependent files; medium: 5–19; broad: 20+. This is not a breakage probability.",
        max_depth=max_depth, truncated=files_truncated or symbols_truncated or count > limit or len(affected_symbols) > limit,
        unresolved_imports=unresolved_imports, unresolved_calls=unresolved_calls,
        files=[dict(file_id=file_id, path=files[file_id].path, depth=file_depth[file_id],
                    via_file_id=file_via.get(file_id), is_test=is_test_file(files[file_id].path))
               for file_id in affected_files[:limit]],
        symbols=[dict(symbol=SymbolRead.model_validate(symbols[symbol_id]).model_dump(),
                      path=files[symbols[symbol_id].file_id].path, depth=symbol_depth[symbol_id],
                      via_symbol_id=symbol_via.get(symbol_id)) for symbol_id in affected_symbols[:limit]],
        limitations=["Only indexed source and resolved import/call candidates are followed.",
                     "JavaScript/TypeScript calls are same-file candidates; imported calls and module aliases remain unresolved.",
                     "Dynamic dispatch, external consumers, and missing/ambiguous targets may hide impact."])


def is_test_file(path):
    parts = path.split("/")
    return ("tests" in parts or "__tests__" in parts or parts[-1].startswith("test_")
            or parts[-1].endswith("_test.py") or any(marker in parts[-1] for marker in (".test.", ".spec.")))


def strongly_connected(forward, reverse):
    visited, order = set(), []
    for root in sorted(forward):
        if root in visited:
            continue
        stack = [(root, False)]
        while stack:
            node, finished = stack.pop()
            if finished:
                order.append(node)
                continue
            if node in visited:
                continue
            visited.add(node)
            stack.append((node, True))
            stack.extend((child, False) for child in sorted(forward[node], reverse=True) if child not in visited)
    visited, groups = set(), []
    for root in reversed(order):
        if root in visited:
            continue
        group, stack = [], [root]
        visited.add(root)
        while stack:
            node = stack.pop()
            group.append(node)
            for child in reverse[node]:
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        if len(group) > 1 or root in forward[root]:
            groups.append(sorted(group))
    return groups


def pagerank(forward, reverse, iterations=30, damping=.85):
    count = len(forward)
    if not count:
        return {}
    scores = {node: 1 / count for node in forward}
    for _ in range(iterations):
        dangling = sum(scores[node] for node in forward if not forward[node]) / count
        scores = {node: (1 - damping) / count + damping * (dangling + sum(
            scores[parent] / len(forward[parent]) for parent in reverse[node])) for node in forward}
    return scores


def architecture(session, repository_id):
    _, snapshot = require_index(session, repository_id)
    files, forward, reverse, unresolved = file_graph(session, repository_id)
    groups = strongly_connected(forward, reverse)
    centrality = pagerank(forward, reverse)
    rows = []
    for file_id, file in files.items():
        content = file.source.encode("utf-8")
        tree = language_parser(file.path).parse(content)
        branches = None if tree.root_node.has_error else 0
        if branches is not None:
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                branches += node.type in {"if_statement", "for_statement", "while_statement", "except_clause",
                                          "boolean_operator", "conditional_expression", "case_clause",
                                          "for_in_statement", "do_statement", "catch_clause", "switch_case", "ternary_expression"}
                if node.type == "binary_expression":
                    operator = node.child_by_field_name("operator")
                    branches += operator is not None and content[operator.start_byte:operator.end_byte] in {b"&&", b"||", b"??"}
                stack.extend(node.named_children)
        coupling = len(reverse[file_id]) + len(forward[file_id])
        rows.append(dict(file_id=file_id, path=file.path, fan_in=len(reverse[file_id]), fan_out=len(forward[file_id]),
                         centrality=round(centrality[file_id], 8), branch_points=branches,
                         review_score=(coupling + 1) * (branches + 1) if branches is not None else None))
    rows.sort(key=lambda row: (-row["centrality"], -row["fan_in"], row["path"]))
    parsing = session.get(ParseSnapshot, repository_id)
    return dict(repository_id=repository_id, commit_sha=snapshot.commit_sha,
        file_count=len(files), dependency_pairs=sum(map(len, forward.values())),
        isolated_files=sum(not forward[node] and not reverse[node] for node in files),
        cycle_component_count=len(groups), cyclic_files=sum(map(len, groups)), unresolved_imports=unresolved,
        parse_error_files=parsing.parse_error_files, pagerank_iterations=30,
        hubs=rows[:50], hotspots=sorted((row for row in rows if row["review_score"] is not None),
                                      key=lambda row: (-row["review_score"], row["path"]))[:20],
        hotspot_rule="(fan-in + fan-out + 1) × (syntax branch points + 1); no Git-history frequency or runtime risk is inferred.",
        import_roots=[row for row in rows if row["fan_in"] == 0 and row["fan_out"] > 0][:50],
        cycles=[dict(files=[dict(file_id=node, path=files[node].path) for node in group[:50]],
                                  size=len(group), truncated=len(group) > 50) for group in sorted(groups, key=lambda group: -len(group))[:50]],
        cycles_truncated=len(groups) > 50,
        limitations=["Metrics use resolved directed file-import edges, not runtime execution.",
                     "Cycle components are strongly connected groups; displayed order is not an edge-by-edge cycle."])
