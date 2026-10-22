"""Supported source languages and pinned, data-only Tree-sitter grammars."""
from functools import lru_cache
from pathlib import PurePosixPath

EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
}
SUPPORTED_LANGUAGES = tuple(dict.fromkeys(EXTENSIONS.values()))
SCRIPT_EXTENSIONS = tuple(extension for extension in EXTENSIONS if extension != ".py")


def language_for_path(path):
    return EXTENSIONS.get(PurePosixPath(path).suffix.lower())


@lru_cache(maxsize=4)
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
    raise ValueError("Unsupported source language.")


def language_parser(path):
    from tree_sitter import Parser
    kind = "TSX" if PurePosixPath(path).suffix.lower() == ".tsx" else language_for_path(path)
    return Parser(syntax_language(kind))
