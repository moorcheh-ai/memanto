import pytest
from fastapi import HTTPException

from memanto.cli.config.manager import ConfigManager
from memanto.cli.schedule_manager import ScheduleManager


@pytest.mark.parametrize("invalid_time", ["9pm", "24:00", "12:60", "12:30:00"])
def test_config_manager_rejects_invalid_schedule_time(tmp_path, invalid_time):
    manager = ConfigManager(config_dir=tmp_path)
    manager.set_schedule_time("08:30")

    with pytest.raises(ValueError, match="HH:MM"):
        manager.set_schedule_time(invalid_time)

    assert manager.get_schedule_time() == "08:30"


@pytest.mark.asyncio
async def test_ui_config_rejects_invalid_schedule_time(tmp_path, monkeypatch):
    from memanto.app.ui.routes import ui_router

    manager = ConfigManager(config_dir=tmp_path)
    manager.set_schedule_time("08:30")
    monkeypatch.setattr(ui_router, "_config_manager", manager)

    with pytest.raises(HTTPException) as exc_info:
        await ui_router.update_ui_config({"schedule_time": "9pm"}, None)

    assert exc_info.value.status_code == 400
    assert manager.get_schedule_time() == "08:30"


def test_schedule_manager_does_not_install_invalid_cron_time(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr("memanto.cli.schedule_manager.subprocess.run", fake_run)
    manager = ScheduleManager()
    manager.os_type = "Darwin"

    result = manager.enable("9pm")

    assert result == {
        "status": "error",
        "message": "Invalid schedule time; expected 24-hour HH:MM format.",
    }
    assert calls == []
