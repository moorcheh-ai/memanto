from memanto.cli.config.manager import ConfigManager


def test_config_sections_with_malformed_shapes_fall_back_to_defaults(tmp_path):
    config_dir = tmp_path / "memanto"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
memanto:
  server: localhost
  session:
    - invalid
  cli: false
  answer: 42
  recall: []
""".strip(),
        encoding="utf-8",
    )

    manager = ConfigManager(config_dir=config_dir)

    assert manager.get_server_url() == "http://localhost:8000"
    assert manager.get_server_config() == {
        "url": "localhost",
        "port": 8000,
        "auto_start": False,
    }
    assert manager.get_session_config()["default_duration_hours"] == 6
    assert manager.get_cli_config()["interactive_mode"] is True
    assert manager.get_answer_config()["answer_limit"] == 15
    assert manager.get_recall_config() == {"limit": 10, "min_similarity": 0.0}
