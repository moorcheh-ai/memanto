"""memanto-cloud backend: config, client factory, and `memanto login` / `logout`."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from memanto.app.clients.backend import Backend
from memanto.app.utils.errors import AuthenticationError
from memanto.cli.client.factory import build_client
from memanto.cli.client.hosted_client import HostedClient
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.commands import auth as auth_module
from memanto.cli.config.manager import DEFAULT_MEMANTO_API_URL, ConfigManager
from memanto.cli.main import app


@pytest.fixture
def cm(tmp_path: Path, monkeypatch) -> ConfigManager:
    """A ConfigManager on an empty dir, with no keys leaking in from the real env."""
    for var in ("MEMANTO_API_KEY", "MEMANTO_API_URL", "MOORCHEH_API_KEY"):
        monkeypatch.setenv(var, "")
    return ConfigManager(config_dir=tmp_path / ".memanto")


def _write_config(cm: ConfigManager, body: str) -> None:
    cm.config_dir.mkdir(parents=True, exist_ok=True)
    cm.config_file.write_text(body)


# Config


def test_existing_cloud_config_still_loads_as_moorcheh_backend(cm):
    _write_config(cm, "memanto:\n  backend: cloud\n")
    assert cm.get_backend() == Backend.CLOUD


def test_memanto_cloud_backend_round_trips(cm):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    assert cm.get_backend() == Backend.MEMANTO_CLOUD
    assert "backend: memanto-cloud" in cm.config_file.read_text()


def test_memanto_cloud_is_configured_only_with_memanto_key(cm):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set_api_key("moorcheh-key")
    assert cm.is_configured() is False

    cm.set_memanto_api_key("mk_abc")
    assert cm.is_configured() is True
    assert "MEMANTO_API_KEY='mk_abc'" in cm.env_file.read_text()

    cm.clear_memanto_api_key()
    assert cm.get_memanto_api_key() is None
    assert "MEMANTO_API_KEY" not in cm.env_file.read_text()


def test_memanto_api_url_defaults_and_overrides(cm, monkeypatch):
    assert cm.get_memanto_api_url() == DEFAULT_MEMANTO_API_URL
    monkeypatch.setenv("MEMANTO_API_URL", "https://staging.test/")
    assert cm.get_memanto_api_url() == "https://staging.test"


# Factory


def test_build_client_returns_hosted_client_on_memanto_cloud(cm):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set_memanto_api_key("mk_abc")

    client = build_client(cm)

    assert isinstance(client, HostedClient)
    assert client.api_key == "mk_abc"
    assert client.base_url == DEFAULT_MEMANTO_API_URL


def test_build_client_requires_login_on_memanto_cloud(cm):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    with pytest.raises(AuthenticationError, match="memanto login"):
        build_client(cm)


def test_build_client_keeps_sdk_client_for_moorcheh_key(cm):
    cm.set_backend(Backend.CLOUD)
    cm.set_api_key("moorcheh-key")

    client = build_client(cm)

    assert type(client) is SdkClient
    assert client.api_key == "moorcheh-key"


# login / logout


@pytest.fixture
def signed_out() -> list[str]:
    """Keys passed to POST /cli/logout, in order."""
    return []


@pytest.fixture
def cli_cm(cm: ConfigManager, monkeypatch, signed_out: list[str]) -> ConfigManager:
    """Point the auth commands at the temp config and keep the real active agent untouched."""
    monkeypatch.setattr(auth_module, "config_manager", cm)
    monkeypatch.setattr(cm, "clear_active_session", lambda: None)

    def sign_out_device(self: HostedClient) -> bool:
        signed_out.append(self._http.headers["x-api-key"])
        return True

    monkeypatch.setattr(HostedClient, "sign_out_device", sign_out_device)
    return cm


def test_login_stores_key_switches_backend_and_remembers_previous(cli_cm, monkeypatch):
    _write_config(cli_cm, "memanto:\n  backend: on-prem\n")
    monkeypatch.setattr(
        HostedClient, "get_account", lambda self: {"email": "dev@example.com"}
    )

    result = CliRunner().invoke(app, ["login", "--key", "mk_abc"])

    assert result.exit_code == 0, result.output
    assert "dev@example.com" in result.output
    assert cli_cm.get_backend() == Backend.MEMANTO_CLOUD
    assert cli_cm.get("previous_backend") == "on-prem"
    assert cli_cm.get_memanto_api_key() == "mk_abc"


def test_login_falls_back_to_list_agents_without_me(cli_cm, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(HostedClient, "get_account", lambda self: None)
    monkeypatch.setattr(
        HostedClient, "list_agents", lambda self: calls.append("list") or {"agents": []}
    )

    result = CliRunner().invoke(app, ["login", "--key", "mk_abc"])

    assert result.exit_code == 0, result.output
    assert calls == ["list"]
    assert cli_cm.get("previous_backend") is None  # fresh install: nothing to restore


def test_login_rejects_bad_key_without_saving(cli_cm, monkeypatch):
    def reject(self):
        raise AuthenticationError("rejected")

    monkeypatch.setattr(HostedClient, "get_account", reject)

    result = CliRunner().invoke(app, ["login", "--key", "mk_bad"])

    assert result.exit_code == 1
    assert "rejected this API key" in result.output
    assert cli_cm.get_memanto_api_key() is None
    assert cli_cm.get_backend() == Backend.CLOUD


def test_logout_restores_previous_backend(cli_cm):
    _write_config(
        cli_cm, "memanto:\n  backend: memanto-cloud\n  previous_backend: on-prem\n"
    )
    cli_cm.set_memanto_api_key("mk_abc")

    result = CliRunner().invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert cli_cm.get_backend() == Backend.ON_PREM
    assert cli_cm.get("previous_backend") is None
    assert cli_cm.get_memanto_api_key() is None


def test_logout_signs_computer_out_on_server(cli_cm, signed_out):
    _write_config(cli_cm, "memanto:\n  backend: memanto-cloud\n")
    cli_cm.set_memanto_api_key("mk_device")

    result = CliRunner().invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert signed_out == ["mk_device"]
    assert "still active" not in result.output


def test_logout_keeps_console_key_active_and_says_so(cli_cm, monkeypatch):
    _write_config(cli_cm, "memanto:\n  backend: memanto-cloud\n")
    cli_cm.set_memanto_api_key("mk_console")
    monkeypatch.setattr(HostedClient, "sign_out_device", lambda self: False)

    result = CliRunner().invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert "still active" in result.output
    assert cli_cm.get_memanto_api_key() is None


@pytest.mark.parametrize(
    ("error", "warned"),
    [(AuthenticationError("gone"), False), (ConnectionError("offline"), True)],
)
def test_logout_clears_locally_even_if_server_call_fails(
    cli_cm, monkeypatch, error, warned
):
    _write_config(cli_cm, "memanto:\n  backend: memanto-cloud\n")
    cli_cm.set_memanto_api_key("mk_device")

    def fail(self):
        raise error

    monkeypatch.setattr(HostedClient, "sign_out_device", fail)

    result = CliRunner().invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert cli_cm.get_memanto_api_key() is None
    assert ("still listed" in result.output) is warned


def test_login_again_retires_previous_key(cli_cm, monkeypatch, signed_out):
    _write_config(cli_cm, "memanto:\n  backend: memanto-cloud\n")
    cli_cm.set_memanto_api_key("mk_old")
    monkeypatch.setattr(HostedClient, "get_account", lambda self: {"email": "a@b.c"})

    result = CliRunner().invoke(app, ["login", "--key", "mk_new"])

    assert result.exit_code == 0, result.output
    assert signed_out == ["mk_old"]
    assert cli_cm.get_memanto_api_key() == "mk_new"


def test_login_with_same_key_keeps_it(cli_cm, monkeypatch, signed_out):
    cli_cm.set_memanto_api_key("mk_same")
    monkeypatch.setattr(HostedClient, "get_account", lambda self: {"email": "a@b.c"})

    result = CliRunner().invoke(app, ["login", "--key", "mk_same"])

    assert result.exit_code == 0, result.output
    assert signed_out == []


def test_failed_login_keeps_previous_key(cli_cm, monkeypatch, signed_out):
    cli_cm.set_memanto_api_key("mk_old")

    def reject(self):
        raise AuthenticationError("rejected")

    monkeypatch.setattr(HostedClient, "get_account", reject)

    result = CliRunner().invoke(app, ["login", "--key", "mk_bad"])

    assert result.exit_code == 1
    assert signed_out == []
    assert cli_cm.get_memanto_api_key() == "mk_old"


def test_logout_when_not_signed_in(cli_cm):
    result = CliRunner().invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "Not signed in" in result.output
