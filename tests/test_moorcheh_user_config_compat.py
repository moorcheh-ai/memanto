"""Regression tests for the moorcheh-client user_config import path.

moorcheh-client 0.1.5 reorganised the package into ``client`` and ``cli``
subpackages, moving ``moorcheh/user_config.py`` to ``moorcheh/cli/user_config.py``.
memanto declares ``moorcheh-client>=0.1.3`` with no upper bound, so a fresh
install resolves to 0.1.5 and the old import path raises ImportError.

That aborted `memanto config backend on-prem` outright:

    Error: moorcheh.user_config unavailable: No module named 'moorcheh.user_config'

which is the documented zero-config local install path. These tests pin the
importer to both layouts.
"""

import sys
import types

import pytest

from memanto.cli.commands.core import _import_user_config

NAMES = ("EmbeddingConfig", "LlmConfig", "default_base_url", "save_runtime_config")


def _fake_user_config_module() -> types.ModuleType:
    mod = types.ModuleType("user_config")
    for name in NAMES:
        setattr(mod, name, type(name, (), {}))
    return mod


@pytest.mark.parametrize("layout", ["new", "old"])
def test_import_user_config_supports_both_layouts(monkeypatch, layout):
    """0.1.5 (moorcheh.cli.user_config) and 0.1.3/0.1.4 (moorcheh.user_config)."""
    for mod in [m for m in sys.modules if m.startswith("moorcheh")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    pkg = types.ModuleType("moorcheh")
    pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "moorcheh", pkg)

    target = _fake_user_config_module()
    if layout == "new":
        cli = types.ModuleType("moorcheh.cli")
        cli.__path__ = []
        monkeypatch.setitem(sys.modules, "moorcheh.cli", cli)
        monkeypatch.setitem(sys.modules, "moorcheh.cli.user_config", target)
    else:
        monkeypatch.setitem(sys.modules, "moorcheh.user_config", target)

    resolved = _import_user_config()
    assert len(resolved) == len(NAMES)
    assert all(obj is not None for obj in resolved)


def test_import_user_config_raises_when_neither_layout_present(monkeypatch):
    """A genuinely missing dependency must still surface as ImportError."""
    for mod in [m for m in sys.modules if m.startswith("moorcheh")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    pkg = types.ModuleType("moorcheh")
    pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "moorcheh", pkg)
    with pytest.raises(ImportError):
        _import_user_config()
