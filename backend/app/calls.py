"""Approximate same-file lexical name matches, never runtime call resolution."""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from .models import CallSite, CallSnapshot, FileParse, SourceFile, Symbol


def match_calls(result):
    definitions = defaultdict(list)
    for index, symbol in enumerate(result.symbols):
        if symbol.symbol_type != "import":
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
                    if not is_class or scope == call.caller_index:
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


def build_calls(session, repository_id, commit_sha, parsed_files):
    for file, result, symbols in parsed_files:
        for call, target, resolution in match_calls(result):
            session.add(CallSite(repository_id=repository_id, file_id=file.id,
                caller_symbol_id=symbols[call.caller_index].id if call.caller_index is not None else None,
                target_symbol_id=symbols[target].id if target is not None else None,
                expression=call.expression, call_type=call.call_type, resolution=resolution,
                start_line=call.start_line, end_line=call.end_line, column=call.column))
    session.add(CallSnapshot(repository_id=repository_id, commit_sha=commit_sha))


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
