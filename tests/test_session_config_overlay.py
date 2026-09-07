"""Session toggles in ~/.memanto/config.yaml must actually reach ``settings``.

The Web UI and ``memanto config`` persist ``session.auto_renew_enabled`` /
``session.auto_recreate_enabled`` to config.yaml, but ``SessionService`` reads
them off ``settings``. The overlay that connects the two runs at import time in
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
    "print(settings.SESSION_AUTO_RENEW_ENABLED, settings.SESSION_AUTO_RECREATE_ENABLED)"
)

_SESSION_ENV_VARS = ("SESSION_AUTO_RENEW_ENABLED", "SESSION_AUTO_RECREATE_ENABLED")


def _run_probe(home, env_overrides=None):
    """Import settings in a fresh process rooted at *home*; return the toggles."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)  # Path.home() on Windows
    for var in _SESSION_ENV_VARS:
        env.pop(var, None)
    env.update(env_overrides or {})

    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    assert result.returncode == 0, result.stderr
    renew, recreate = result.stdout.split()
    return renew == "True", recreate == "True"


@pytest.fixture
def home_with_session_config(tmp_path):
    """Build a throwaway HOME and write the given session block into it."""

    def _write(body):
        config_dir = tmp_path / ".memanto"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.yaml").write_text(body)
        return tmp_path

    return _write


def test_yaml_toggles_reach_settings(home_with_session_config):
    """Turning the toggles off in config.yaml disables them for the services."""
    home = home_with_session_config(
        "memanto:\n"
        "  session:\n"
        "    auto_renew_enabled: false\n"
        "    auto_recreate_enabled: false\n"
    )

    assert _run_probe(home) == (False, False)


def test_environment_overrides_yaml(home_with_session_config):
    """An explicit SESSION_AUTO_* env var wins over config.yaml.

    Containerised deployments configure MEMANTO through the environment and
    must not be silently overridden by a config.yaml mounted from the host.
    """
    home = home_with_session_config(
        "memanto:\n"
        "  session:\n"
        "    auto_renew_enabled: false\n"
        "    auto_recreate_enabled: false\n"
    )

    assert _run_probe(home, {"SESSION_AUTO_RECREATE_ENABLED": "true"}) == (False, True)


def test_missing_or_malformed_config_keeps_defaults(home_with_session_config):
    """Absent, non-boolean, or unparsable config leaves the defaults standing."""
    empty_home = home_with_session_config("")
    assert _run_probe(empty_home) == (True, True)

    wrong_type = home_with_session_config(
        "memanto:\n  session:\n    auto_recreate_enabled: 'maybe'\n"
    )
    assert _run_probe(wrong_type) == (True, True)

    not_a_mapping = home_with_session_config("memanto:\n  session: []\n")
    assert _run_probe(not_a_mapping) == (True, True)
