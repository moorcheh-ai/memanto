from unittest.mock import MagicMock, patch

import pytest

from memanto.cli.config.manager import ConfigManager
from memanto.cli.schedule_manager import ScheduleManager


def test_unix_schedule_rejects_invalid_time_before_crontab_write():
    manager = ScheduleManager()

    with patch("memanto.cli.schedule_manager.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="")

        result = manager._enable_unix("not-a-time")

    assert result["status"] == "error"
    assert "HH:MM" in result["message"]
    assert all(call.args[0] != ["crontab", "-"] for call in mock_run.call_args_list)


def test_unix_schedule_accepts_valid_time_and_writes_normalized_cron():
    manager = ScheduleManager()

    def _run(command, capture_output=False, text=False, check=False, input=None):
        if command == ["crontab", "-l"]:
            return MagicMock(stdout="# existing cron\n")
        if command == ["crontab", "-"]:
            assert input is not None
            assert "5 7 * * *" in input
            assert "07:05" not in input
            return MagicMock()
        raise AssertionError(command)

    with patch("memanto.cli.schedule_manager.subprocess.run", side_effect=_run):
        result = manager._enable_unix("7:05")

    assert result["status"] == "success"
    assert "07:05" in result["message"]


def test_config_manager_rejects_invalid_schedule_time(tmp_path):
    manager = ConfigManager(config_dir=tmp_path)

    with pytest.raises(ValueError, match="HH:MM"):
        manager.set_schedule_time("25:61")
