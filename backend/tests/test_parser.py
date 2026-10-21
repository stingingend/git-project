import pytest

from app.parser import ParsingError, parse_python


def test_functions_classes_methods_and_nested_scopes():
    result = parse_python('''class PaymentService:
    async def charge(self, customer):
        def validate():
            return True
        return validate()

def checkout(items):
    return items
''', "src/payments.py")
    assert not result.has_parse_errors
    assert [(s.name, s.symbol_type, s.start_line, s.end_line) for s in result.symbols] == [
        ("PaymentService", "class", 1, 5), ("charge", "method", 2, 5),
        ("validate", "function", 3, 4), ("checkout", "function", 7, 8),
    ]
    charge = result.symbols[1]
    assert charge.qualified_name == "src/payments.py::PaymentService.charge"
    assert charge.parent_qualified_name == "src/payments.py::PaymentService"
    assert charge.signature == "async def charge(self, customer)"
    assert result.symbols[2].parent_qualified_name == charge.qualified_name
    assert result.symbols[3].parent_qualified_name is None


def test_decorated_unicode_and_multiline_signatures():
    result = parse_python('''@decorator
def café(
    value: str,
) -> str:
    """A docstring."""
    return value
''', "cafe.py")
    symbol = result.symbols[0]
    assert symbol.name == "café"
    assert symbol.start_line == 2  # definitions start at def, not decorators
    assert symbol.end_line == 6
    assert symbol.signature == "def café(\n    value: str,\n) -> str"


def test_import_statements_include_future_relative_and_scoped_imports():
    result = parse_python('''from __future__ import annotations
import os, json as json_module
from . import helper
from package import (
    first,
    second,
)
def load():
    import local
''', "module.py")
    imports = [s for s in result.symbols if s.symbol_type == "import"]
    assert len(imports) == 5  # statements, not imported names
    assert imports[0].name == "from __future__ import annotations"
    assert imports[1].qualified_name == "module.py::import@2:0"
    assert imports[3].start_line == 4 and imports[3].end_line == 7
    assert imports[4].parent_qualified_name == "module.py::load"


def test_overloads_keep_separate_source_ranges():
    result = parse_python('''class Example:
    @staticmethod
    def load(value: str): ...
    @staticmethod
    def load(value: bytes): ...
''', "example.py")
    methods = [s for s in result.symbols if s.symbol_type == "method"]
    assert len(methods) == 2
    assert methods[0].qualified_name == methods[1].qualified_name
    assert [s.start_line for s in methods] == [3, 5]


def test_syntax_errors_are_flagged_and_recovered_symbols_remain_available():
    result = parse_python("def valid():\n    return 1\n\ndef broken(:\n", "broken.py")
    assert result.has_parse_errors
    assert any(s.name == "valid" for s in result.symbols)


def test_empty_source_and_deep_trees():
    assert parse_python("", "empty.py").symbols == []
    source = "value = " + "(" * 1500 + "1" + ")" * 1500 + "\ndef hello():\n    return value\n"
    result = parse_python(source, "deep.py")
    assert not result.has_parse_errors
    assert result.symbols[0].name == "hello"


def test_symbol_limit():
    with pytest.raises(ParsingError, match="symbol limit"):
        parse_python("def hello(): pass\n", "module.py", max_symbols=0)


def test_large_module_with_nested_definitions():
    source = "class Serializer:\n"
    for number in range(100):
        source += f'''    def load_{number}(self, value: str) -> str:
        def normalize(item):
            return item.strip()
        return normalize(value)
'''
    result = parse_python(source, "serializer.py")
    assert not result.has_parse_errors
    assert sum(s.symbol_type == "method" for s in result.symbols) == 100
    assert sum(s.symbol_type == "function" for s in result.symbols) == 100
