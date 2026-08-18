"""Dependency-bound regressions.

The declared bounds are load-bearing: this server imports modules that exist
only in specific dependency majors, and a resolver is free to pick anything a
bound allows. These tests read the real metadata rather than the environment,
so a loosened pin fails here instead of in a user's fresh install.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

tomllib = pytest.importorskip("tomllib")

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _requirement(name: str) -> Requirement:
    """Return the declared runtime requirement for *name*."""
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    for raw in metadata["project"]["dependencies"]:
        requirement = Requirement(raw)
        if requirement.name == name:
            return requirement
    raise AssertionError(f"{name} is not declared in [project.dependencies]")


def test_mcp_dependency_excludes_v2() -> None:
    """mcp 2.0 deleted `mcp.server.fastmcp`, which server.py imports.

    Without an upper bound a fresh install resolves to 2.x and dies at import
    with "No module named 'mcp.server.fastmcp'".
    """
    specifier = _requirement("mcp").specifier

    assert not specifier.contains(Version("2.0.0"))
    assert specifier.contains(Version("1.29.0"))


def test_memanto_dependency_requires_open_sources() -> None:
    """tools.py imports MemorySource/is_valid_source, added in memanto 0.2.13.

    0.2.11 and 0.2.12 also reject the open source labels this server writes.
    """
    specifier = _requirement("memanto").specifier

    assert not specifier.contains(Version("0.2.12"))
    assert specifier.contains(Version("0.2.13"))
