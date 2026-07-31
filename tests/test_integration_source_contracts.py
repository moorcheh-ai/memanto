"""Contract checks for source literals used by optional integrations."""

import ast
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from memanto.app.constants import SourceType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS_ROOT = PROJECT_ROOT / "integrations"
SOURCE_ADAPTER = TypeAdapter(SourceType)


def _iter_source_literals(path: Path):
    """Yield line numbers and literal values assigned to integration sources."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "source" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        yield keyword.value.lineno, keyword.value.value

        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "source"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    yield value.lineno, value.value


def test_shipped_integration_source_literals_match_core_contract():
    """Require shipped integration source literals to satisfy ``SourceType``."""
    invalid_sources: list[str] = []

    for path in sorted(INTEGRATIONS_ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue

        for line, source in _iter_source_literals(path):
            try:
                SOURCE_ADAPTER.validate_python(source)
            except ValidationError:
                relative_path = path.relative_to(PROJECT_ROOT)
                invalid_sources.append(f"{relative_path}:{line}: {source!r}")

    assert invalid_sources == []
