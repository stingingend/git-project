"""Supported source languages and pinned, data-only Tree-sitter grammars."""
from functools import lru_cache
from pathlib import PurePosixPath

EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
    ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".c++": "C++", ".hpp": "C++", ".hh": "C++", ".hxx": "C++", ".h++": "C++",
    ".ipp": "C++", ".tpp": "C++", ".inl": "C++",
}
SUPPORTED_LANGUAGES = tuple(dict.fromkeys(EXTENSIONS.values()))
SCRIPT_EXTENSIONS = tuple(extension for extension, language in EXTENSIONS.items() if language in {"JavaScript", "TypeScript"})


def language_for_path(path, source=None):
    suffix = PurePosixPath(path).suffix
    if suffix == ".C":
        return "C++"
    language = EXTENSIONS.get(suffix.lower())
    if suffix.lower() == ".h" and source is not None:
        from tree_sitter import Parser
        content = source.encode("utf-8")
        c_tree = Parser(syntax_language("C")).parse(content)
        cpp_tree = Parser(syntax_language("C++")).parse(content)
        # The C grammar can accept some C++ constructs as unusual declarations.
        # Inspect syntax nodes, not text, so comments and strings cannot decide.
        stack = [cpp_tree.root_node]
        cpp_constructs = {"namespace_definition", "class_specifier", "template_declaration",
                          "alias_declaration", "linkage_specification", "reference_declarator"}
        while stack:
            node = stack.pop()
            if node.type in cpp_constructs and not cpp_tree.root_node.has_error:
                return "C++"
            stack.extend(node.named_children)
        if c_tree.root_node.has_error:
            if not cpp_tree.root_node.has_error:
                return "C++"
            def errors(root):
                count, stack = 0, [root]
                while stack:
                    node = stack.pop()
                    count += node.is_error or node.is_missing
                    stack.extend(node.children)
                return count
            if errors(cpp_tree.root_node) < errors(c_tree.root_node):
                return "C++"
    return language


@lru_cache(maxsize=6)
def syntax_language(path_kind):
    from tree_sitter import Language
    if path_kind == "Python":
        from .parser import PYTHON
        return PYTHON
    if path_kind == "JavaScript":
        import tree_sitter_javascript
        return Language(tree_sitter_javascript.language())
    if path_kind in {"TypeScript", "TSX"}:
        import tree_sitter_typescript
        return Language(tree_sitter_typescript.language_tsx() if path_kind == "TSX"
                        else tree_sitter_typescript.language_typescript())
    if path_kind == "C":
        import tree_sitter_c
        return Language(tree_sitter_c.language())
    if path_kind == "C++":
        import tree_sitter_cpp
        return Language(tree_sitter_cpp.language())
    raise ValueError("Unsupported source language.")


def language_parser(path, source=None, language=None):
    from tree_sitter import Parser
    kind = "TSX" if PurePosixPath(path).suffix.lower() == ".tsx" else language or language_for_path(path, source)
    return Parser(syntax_language(kind))
