"""Extract syntax only: never import, compile, or execute repository source."""
from dataclasses import dataclass, field

import tree_sitter_python
from tree_sitter import Language, Parser

PYTHON = Language(tree_sitter_python.language())
IMPORT_NODES = {"import_statement", "import_from_statement", "future_import_statement"}


class ParsingError(ValueError):
    pass


@dataclass
class ExtractedSymbol:
    name: str
    qualified_name: str
    parent_qualified_name: str | None
    symbol_type: str
    start_line: int
    end_line: int
    signature: str


@dataclass
class ExtractedCall:
    expression: str
    direct_name: str | None
    caller_index: int | None
    call_type: str
    start_line: int
    end_line: int
    column: int


@dataclass
class ParsedFile:
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    has_parse_errors: bool = False
    # Identity preserves the exact enclosing definition even for repeated names.
    parents: list[int | None] = field(default_factory=list)
    calls: list[ExtractedCall] = field(default_factory=list)


def parse_python(source: str, path: str, max_symbols: int = 100_000,
                 max_calls: int = 100_000) -> ParsedFile:
    content = source.encode("utf-8")
    parser = Parser(PYTHON)
    tree = parser.parse(content)
    result = ParsedFile(has_parse_errors=tree.root_node.has_error)

    def text(node):
        return content[node.start_byte:node.end_byte].decode("utf-8")

    # Each entry carries its nearest enclosing definition. Iteration avoids the
    # Python recursion limit for deeply nested trees and large expressions.
    stack = [(tree.root_node, None)]
    positions = {}
    while stack:
        node, parent = stack.pop()
        next_parent = parent
        if node.type in {"function_definition", "class_definition"}:
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node is not None and body is not None:
                name = text(name_node)
                kind = "class" if node.type == "class_definition" else (
                    "method" if parent is not None and parent.symbol_type == "class" else "function"
                )
                parent_name = parent.qualified_name if parent else None
                qualified = f"{parent_name}.{name}" if parent_name else f"{path}::{name}"
                signature = content[node.start_byte:body.start_byte].decode("utf-8").strip().removesuffix(":")
                next_parent = ExtractedSymbol(name, qualified, parent_name, kind,
                    node.start_point.row + 1, node.end_point.row + 1, signature)
                result.symbols.append(next_parent)
                result.parents.append(positions[id(parent)] if parent else None)
                positions[id(next_parent)] = len(result.symbols) - 1
        elif node.type in IMPORT_NODES:
            statement = text(node)
            result.symbols.append(ExtractedSymbol(statement,
                f"{path}::import@{node.start_point.row + 1}:{node.start_point.column}",
                parent.qualified_name if parent else None, "import",
                node.start_point.row + 1, node.end_point.row + 1, statement))
            result.parents.append(positions[id(parent)] if parent else None)
        elif node.type == "call":
            function = node.child_by_field_name("function")
            if function is not None:
                direct = function.type == "identifier"
                # Dynamic expressions can nest deeply: do not repeatedly decode
                # an entire expression when only a short display label is saved.
                expression = text(function) if direct else content[function.start_byte:
                    min(function.end_byte, function.start_byte + 1200)].decode("utf-8", errors="ignore")[:300]
                result.calls.append(ExtractedCall(expression[:300], expression if direct else None,
                    positions[id(parent)] if parent else None,
                    "direct" if direct else "attribute" if function.type == "attribute" else "dynamic",
                    node.start_point.row + 1, node.end_point.row + 1, node.start_point.column + 1))
                if len(result.calls) > max_calls:
                    raise ParsingError("Repository exceeds the 100,000 call limit.")
        if len(result.symbols) > max_symbols:
            raise ParsingError("Repository exceeds the 100,000 symbol limit.")
        stack.extend((child, next_parent) for child in reversed(node.named_children))
    return result
