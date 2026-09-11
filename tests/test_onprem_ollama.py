from unittest.mock import Mock, call

from moorcheh import ollama_setup

from memanto.cli.commands import core


def test_pull_ollama_model_uses_host_http_when_native_ollama_is_reachable(
    monkeypatch,
):
    http_pull = Mock()
    container_pull = Mock()
    monkeypatch.setattr(ollama_setup, "ollama_is_reachable", lambda: True)
    monkeypatch.setattr(ollama_setup, "pull_ollama_model_http", http_pull)
    monkeypatch.setattr(core, "_pull_ollama_model_in_container", container_pull)

    core._pull_ollama_model("nomic-embed-text")

    http_pull.assert_called_once_with("nomic-embed-text")
    container_pull.assert_not_called()


def test_pull_ollama_model_falls_back_to_container_when_host_is_unreachable(
    monkeypatch,
):
    http_pull = Mock()
    container_pull = Mock()
    monkeypatch.setattr(ollama_setup, "ollama_is_reachable", lambda: False)
    monkeypatch.setattr(ollama_setup, "pull_ollama_model_http", http_pull)
    monkeypatch.setattr(core, "_pull_ollama_model_in_container", container_pull)

    core._pull_ollama_model("nomic-embed-text")

    http_pull.assert_not_called()
    container_pull.assert_called_once_with("nomic-embed-text")


def test_onprem_setup_routes_ollama_models_through_shared_pull_helper(monkeypatch):
    state = {
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "llm_provider": "ollama",
        "llm_model": "qwen2.5",
    }
    pull_model = Mock()
    container_pull = Mock()

    monkeypatch.setattr(core, "_ensure_docker_available", Mock())
    monkeypatch.setattr(core, "_ensure_moorcheh_client_installed", Mock())
    monkeypatch.setattr(core.config_manager, "get_onprem_state", lambda: state)
    monkeypatch.setattr(core, "_persist_moorcheh_llm_config", Mock())
    monkeypatch.setattr(core, "_moorcheh_up_and_wait", Mock())
    monkeypatch.setattr(core, "_pull_ollama_model", pull_model)
    monkeypatch.setattr(core, "_pull_ollama_model_in_container", container_pull)
    monkeypatch.setattr(core.config_manager, "set_onprem_state", Mock())

    core._onprem_setup()

    assert pull_model.call_args_list == [
        call("nomic-embed-text"),
        call("qwen2.5"),
    ]
    container_pull.assert_not_called()
