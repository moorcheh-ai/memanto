"""The auto-activate toggle in ~/.memanto/config.yaml must actually reach ``settings``.

The Web UI and ``memanto agent auto-activate`` persist
``session.auto_activate_enabled`` to config.yaml, but ``SessionService`` reads
it off ``settings``. The overlay that connects the two runs at import time in
``memanto.app.config``, so these tests exercise it in a subprocess with a
throwaway HOME rather than reloading the module (which would rebuild the
``settings`` singleton other tests already hold a reference to).
"""

import os
import subprocess
import sys

import pytest

_PROBE = (
    "from memanto.app.config import settings;"
    "print(settings.SESSION_AUTO_ACTIVATE_ENABLED)"
)


def _run_probe(home, env_overrides=None):
    """Import settings in a fresh process rooted at *home*; return the toggle."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)  # Path.home() on Windows
    env.pop("SESSION_AUTO_ACTIVATE_ENABLED", None)
    env.update(env_overrides or {})

    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip() == "True"


@pytest.fixture
def home_with_session_config(tmp_path):
    """Build a throwaway HOME and write the given session block into it."""

    def _write(body):
        config_dir = tmp_path / ".memanto"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.yaml").write_text(body)
        return tmp_path

    return _write


def test_yaml_toggle_reaches_settings(home_with_session_config):
    """Fresh processes (hooks, MCP, widget) pick up the toggle."""
    home = home_with_session_config(
        "memanto:\n  session:\n    auto_activate_enabled: true\n"
    )
    assert _run_probe(home) is True


def test_environment_overrides_yaml(home_with_session_config):
    """An explicit SESSION_AUTO_ACTIVATE_ENABLED env var wins over config.yaml.

    Containerised deployments configure MEMANTO through the environment and
    must not be silently overridden by a config.yaml mounted from the host.
    """
    home = home_with_session_config(
        "memanto:\n  session:\n    auto_activate_enabled: true\n"
    )
    assert _run_probe(home, {"SESSION_AUTO_ACTIVATE_ENABLED": "false"}) is False


def test_missing_or_malformed_config_keeps_default_off(home_with_session_config):
    """Absent, non-boolean, or unparsable config leaves the default (off)."""
    assert _run_probe(home_with_session_config("")) is False
    wrong_type = home_with_session_config(
        "memanto:\n  session:\n    auto_activate_enabled: 'maybe'\n"
    )
    assert _run_probe(wrong_type) is False
    not_a_mapping = home_with_session_config("memanto:\n  session: []\n")
    assert _run_probe(not_a_mapping) is False


def test_removed_toggles_are_ignored(home_with_session_config):
    """Old auto_renew/auto_recreate keys in an existing config.yaml are inert."""
    home = home_with_session_config(
        "memanto:\n"
        "  session:\n"
        "    auto_renew_enabled: true\n"
        "    auto_recreate_enabled: true\n"
    )
    assert _run_probe(home) is False
