from memanto.cli.config.manager import ConfigManager


def test_config_setters_recover_malformed_sections(tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    manager.config_file.write_text(
        "\n".join(
            [
                "memanto:",
                "  server: localhost",
                "  session: 6",
                "  cli: false",
                "  answer: 42",
                "  recall:",
                "    - invalid",
                "",
            ]
        )
    )

    assert manager.get_server_url() == "http://localhost:8000"
    assert manager.get_server_config() == {
        "url": "localhost",
        "port": 8000,
        "auto_start": False,
    }
    assert manager.get_session_config()["default_duration_hours"] == 6
    assert manager.get_cli_config()["interactive_mode"] is True
    assert manager.get_answer_config()["model"] == "anthropic.claude-sonnet-4-6"
    assert manager.get_recall_config() == {"limit": 10, "min_similarity": 0.0}

    manager.set_server_config("127.0.0.1", 9999)
    manager.set_cli_config(interactive_mode=False, smart_parse=False)
    manager.set_answer_config(model="local-model", temperature=0.2)
    manager.set_recall_config(limit=7, min_similarity=0.4)

    data = manager.load_yaml()

    assert data["server"] == {"url": "127.0.0.1", "port": 9999}
    assert data["cli"] == {"interactive_mode": False, "smart_parse": False}
    assert data["answer"]["model"] == "local-model"
    assert data["answer"]["temperature"] == 0.2
    assert data["recall"] == {"limit": 7, "min_similarity": 0.4}
