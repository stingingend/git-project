"""C/C++ source structure without a compiler, preprocessor, or build execution."""
import posixpath
import re

from .languages import language_parser
from .parser import ExtractedCall, ExtractedSymbol, ParsedFile, ParsingError

SCOPES = {"class_specifier": "class", "struct_specifier": "struct", "union_specifier": "union",
          "enum_specifier": "enum", "namespace_definition": "namespace"}


def function_name(declarator):
    """Follow the declarator spine, never parameter identifiers or pointer variables."""
    current = declarator
    while current is not None:
        if current.type == "operator_cast":
            return current
        if current.type == "function_declarator":
            name = current.child_by_field_name("declarator")
            if name is not None and name.type in {
                "identifier", "field_identifier", "qualified_identifier", "operator_name",
                "destructor_name", "template_function"}:
                return name
        child = current.child_by_field_name("declarator")
        if child is None and current.type == "parenthesized_declarator" and len(current.named_children) == 1:
            child = current.named_children[0]
        current = child
    return None


def include_target(path, statement, files_by_path):
    match = re.match(r'\s*#\s*include\s*(?:"([^"\n]+)"|<([^>\n]+)>)', statement)
    if match is None:
        return statement.strip(), None, "unresolved"
    specifier = match[1] or match[2]
    if "\\" in specifier or specifier.startswith("/"):
        return specifier, None, "unresolved"
    tiers = []
    if match[1]:
        tiers.append([posixpath.normpath(posixpath.join(posixpath.dirname(path), specifier))])
    # No build flags are evaluated. These two conventional repository roots
    # are candidates in the same tier, so collisions remain ambiguous.
    tiers.append([posixpath.normpath(specifier), posixpath.normpath(posixpath.join("include", specifier))])
    for tier in tiers:
        matches = {files_by_path[candidate] for candidate in tier
                   if not candidate.startswith(("../", "/")) and candidate != ".." and candidate in files_by_path}
        if matches:
            return (specifier, next(iter(matches)), "local") if len(matches) == 1 else (specifier, None, "ambiguous")
    return specifier, None, "unresolved"


def parse_native(source, path, max_symbols=100_000, max_calls=100_000, language=None):
    content = source.encode("utf-8")
    tree = language_parser(path, source, language).parse(content)
    result = ParsedFile(has_parse_errors=tree.root_node.has_error)

    def text(node, limit=None):
        stop = node.end_byte if limit is None else min(node.end_byte, node.start_byte + limit)
        return content[node.start_byte:stop].decode("utf-8", errors="ignore")

    def add(node, parent, name, kind, body=None, scoped=False):
        start = node.parent if node.parent is not None and node.parent.type == "template_declaration" else node
        parent_name = result.symbols[parent].qualified_name if parent is not None else None
        qualified = f"{parent_name}.{name}" if parent_name else f"{path}::{name}"
        end = body.start_byte if body is not None else node.end_byte
        signature = content[start.start_byte:min(end, start.start_byte + 1200)].decode("utf-8", errors="ignore").strip()
        result.symbols.append(ExtractedSymbol(name, qualified, parent_name, kind,
            start.start_point.row + 1, max(start.start_point.row + 1, node.end_point.row + bool(node.end_point.column)), signature))
        result.parents.append(parent)
        if len(result.symbols) > max_symbols:
            raise ParsingError("Repository exceeds the 100,000 symbol limit.")
        return len(result.symbols) - 1 if scoped else parent

    def callable_name(node):
        return text(node).split("(", 1)[0].strip() if node.type == "operator_cast" else text(node)

    stack = [(tree.root_node, None)]
    while stack:
        node, parent = stack.pop()
        next_parent = parent
        name = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if node.type in SCOPES and name is not None and body is not None:
            next_parent = add(node, parent, text(name), SCOPES[node.type], body, scoped=True)
        elif node.type == "function_definition":
            name = function_name(node.child_by_field_name("declarator"))
            if name is not None:
                kind = "method" if parent is not None and result.symbols[parent].symbol_type in {"class", "struct", "union"} else "function"
                next_parent = add(node, parent, callable_name(name), kind, body, scoped=True)
        elif node.type in {"declaration", "field_declaration"}:
            for declarator in node.children_by_field_name("declarator"):
                name = function_name(declarator)
                if name is not None:
                    add(node, parent, callable_name(name), "declaration")
        elif node.type == "type_definition":
            for declarator in node.children_by_field_name("declarator"):
                current = declarator
                while current is not None and current.type not in {"type_identifier", "identifier"}:
                    child = current.child_by_field_name("declarator")
                    if child is None and current.type == "parenthesized_declarator" and len(current.named_children) == 1:
                        child = current.named_children[0]
                    current = child
                if current is not None:
                    add(node, parent, text(current), "type")
        elif node.type == "alias_declaration" and name is not None:
            add(node, parent, text(name), "type")
        elif node.type in {"preproc_def", "preproc_function_def"} and name is not None:
            add(node, parent, text(name), "macro")
        elif node.type == "preproc_include":
            add(node, parent, text(node), "import")
        elif node.type == "lambda_expression" and node.parent is not None and node.parent.type == "init_declarator":
            binding = node.parent.child_by_field_name("declarator")
            if binding is not None and binding.type == "identifier":
                next_parent = add(node, parent, text(binding), "function", body, scoped=True)
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                expression = text(function, 1200)[:300]
                direct = function.type == "identifier"
                result.calls.append(ExtractedCall(expression, expression if direct else None, parent,
                    "direct" if direct else "attribute" if function.type == "field_expression" else "dynamic",
                    node.start_point.row + 1, node.end_point.row + 1, node.start_point.column + 1))
                if len(result.calls) > max_calls:
                    raise ParsingError("Repository exceeds the 100,000 call limit.")
        stack.extend((child, next_parent) for child in reversed(node.named_children))
    return result
