"""JavaScript/TypeScript syntax extraction. Source is never executed."""
import ast

from .languages import language_parser
from .parser import ExtractedCall, ExtractedSymbol, ParsedFile, ParsingError

FUNCTIONS = {"function_declaration", "generator_function_declaration", "function_expression",
             "generator_function", "arrow_function"}


def literal_string(node, content):
    if node is None or node.type != "string":
        return None
    value = content[node.start_byte:node.end_byte].decode("utf-8")
    try:
        decoded = ast.literal_eval(value)
        return decoded if isinstance(decoded, str) else None
    except (SyntaxError, ValueError, RecursionError):
        return None


def module_reference(node, content):
    if node.type in {"import_statement", "export_statement"}:
        return literal_string(node.child_by_field_name("source"), content)
    if node.type == "call_expression":
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is not None and content[function.start_byte:function.end_byte] in {b"require", b"import"}:
            args = arguments.named_children if arguments is not None else []
            if len(args) == 1:
                return literal_string(args[0], content)
    return None


def script_modules(statement, path):
    content = statement.encode("utf-8")
    root = language_parser(path).parse(content).root_node
    stack, modules = [root], []
    while stack:
        node = stack.pop()
        module = module_reference(node, content)
        if module is not None:
            modules.append(module)
        stack.extend(reversed(node.named_children))
    return list(dict.fromkeys(modules))


def parse_script(source, path, max_symbols=100_000, max_calls=100_000):
    content = source.encode("utf-8")
    tree = language_parser(path).parse(content)
    result = ParsedFile(has_parse_errors=tree.root_node.has_error)

    def text(node):
        return content[node.start_byte:node.end_byte].decode("utf-8")

    def add(node, parent, name, kind, signature):
        parent_name = result.symbols[parent].qualified_name if parent is not None else None
        qualified = f"{parent_name}.{name}" if parent_name else f"{path}::{name}"
        result.symbols.append(ExtractedSymbol(name, qualified, parent_name, kind,
            node.start_point.row + 1, node.end_point.row + 1, signature))
        result.parents.append(parent)
        if len(result.symbols) > max_symbols:
            raise ParsingError("Repository exceeds the 100,000 symbol limit.")
        return len(result.symbols) - 1

    stack = [(tree.root_node, None)]
    while stack:
        node, parent = stack.pop()
        next_parent = parent
        name_node = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        kind, name = None, None
        if node.type in {"class_declaration", "class"}:
            kind = "class"
        elif node.type == "method_definition":
            kind = "method"
        elif node.type in FUNCTIONS:
            kind = "function"
            # A bound arrow/function expression is indexed under its binding,
            # rather than creating anonymous noise for every callback.
            if node.parent is not None and node.parent.type in {"variable_declarator", "pair", "public_field_definition", "field_definition"}:
                binding = node.parent.child_by_field_name("name") or node.parent.child_by_field_name("key") or node.parent.child_by_field_name("property")
                if binding is not None and binding.type in {"identifier", "property_identifier", "private_property_identifier"}:
                    name = text(binding)
                    if node.parent.type in {"public_field_definition", "field_definition"}:
                        kind = "method"
        elif node.type == "interface_declaration":
            kind = "interface"
        elif node.type == "type_alias_declaration":
            kind = "type"
        if kind is not None:
            if name is None and name_node is None and node.parent is not None:
                if node.parent.type == "variable_declarator":
                    binding = node.parent.child_by_field_name("name")
                    if binding is not None and binding.type == "identifier":
                        name = text(binding)
                elif node.parent.type == "export_statement" and any(child.type == "default" for child in node.parent.children):
                    name = "default"
            name = name or (text(name_node) if name_node is not None else None)
            # Destructuring/computed method names are not stable identifiers.
            if name and (name_node is None or name_node.type != "computed_property_name"):
                end = body.start_byte if body is not None else min(node.end_byte, node.start_byte + 1200)
                signature = content[node.start_byte:end].decode("utf-8", errors="ignore").strip()[:1200]
                next_parent = add(node, parent, name, kind, signature)
        module = module_reference(node, content)
        if module is not None:
            statement = text(node)
            add(node, parent, statement, "import", statement)
        if node.type in {"call_expression", "new_expression"}:
            function = node.child_by_field_name("function") or node.child_by_field_name("constructor")
            if function is not None:
                expression = content[function.start_byte:min(function.end_byte, function.start_byte + 1200)].decode("utf-8", errors="ignore")[:300]
                direct = function.type == "identifier"
                result.calls.append(ExtractedCall(expression, expression if direct else None, parent,
                    "direct" if direct else "attribute" if function.type == "member_expression" else "dynamic",
                    node.start_point.row + 1, node.end_point.row + 1, node.start_point.column + 1))
                if len(result.calls) > max_calls:
                    raise ParsingError("Repository exceeds the 100,000 call limit.")
        stack.extend((child, next_parent) for child in reversed(node.named_children))
    return result
