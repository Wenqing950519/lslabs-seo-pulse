import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / 'seo_pulse_mcp'
TEXT_IO = {'read_text', 'write_text', 'open', 'fdopen'}


def _missing_encoding(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, 'attr', None) or getattr(node.func, 'id', None)
        if name not in TEXT_IO:
            continue
        mode = next((a.value for a in node.args[1:2] if isinstance(a, ast.Constant)), None)
        mode = next((k.value.value for k in node.keywords if k.arg == 'mode' and isinstance(k.value, ast.Constant)), mode)
        if isinstance(mode, str) and 'b' in mode:
            continue
        if not any(k.arg == 'encoding' for k in node.keywords):
            yield node.lineno


def test_text_io_declares_encoding():
    # Windows defaults to the locale code page (e.g. cp950), which cannot decode the UTF-8 fixtures.
    missing = [f'{path.relative_to(PACKAGE)}:{line}'
               for path in PACKAGE.rglob('*.py')
               for line in _missing_encoding(ast.parse(path.read_text(encoding='utf-8')))]
    assert missing == []
