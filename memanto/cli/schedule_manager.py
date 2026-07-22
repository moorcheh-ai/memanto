"""
Schedule Manager for MEMANTO.

Schedules a nightly job that runs daily-summary followed by detect-conflicts
(via the internal ``memanto schedule _run`` entrypoint).
"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


class ScheduleManager:
    """Manages OS-level scheduled tasks for MEMANTO."""

    TASK_NAME = "MemantoNightlyJob"
    LEGACY_TASK_NAMES = ("MemantoDailySummary",)

    def __init__(self):
        self.os_type = platform.system()
        self.cli_main = Path(__file__).parent / "main.py"
        self.python_exe = sys.executable

    def _remove_legacy_tasks(self) -> None:
        """Best-effort removal of older task identities so upgrades don't
        leave duplicate nightly jobs running alongside the current one."""
        if self.os_type == "Windows":
            for name in self.LEGACY_TASK_NAMES:
                subprocess.run(
                    ["schtasks", "/delete", "/tn", name, "/f"],
                    capture_output=True,
                    text=True,
                )
        else:
            try:
                current_cron = subprocess.run(
                    ["crontab", "-l"], capture_output=True, text=True
                ).stdout
                legacy_markers = [f"# {name}" for name in self.LEGACY_TASK_NAMES]
                lines = [
                    line
                    for line in current_cron.splitlines()
                    if not any(m in line for m in legacy_markers)
                ]
                if len(lines) != len(current_cron.splitlines()):
                    new_cron = "\n".join(lines).rstrip() + "\n"
                    subprocess.run(
                        ["crontab", "-"], input=new_cron, text=True, check=False
                    )
            except Exception:
                pass

    def _command(self) -> str:
        return f'"{self.python_exe}" "{self.cli_main.absolute()}" schedule _run'

    def enable(self, time_str: str = "23:55") -> dict[str, Any]:
        self._remove_legacy_tasks()
        if self.os_type == "Windows":
            return self._enable_windows(time_str)
        return self._enable_unix(time_str)

    def disable(self) -> dict[str, Any]:
        self._remove_legacy_tasks()
        if self.os_type == "Windows":
            return self._disable_windows()
        return self._disable_unix()

    def get_status(self) -> dict[str, Any]:
        if self.os_type == "Windows":
            return self._status_windows()
        return self._status_unix()

    # Windows (schtasks)

    def _enable_windows(self, time_str: str = "23:55") -> dict[str, Any]:
        command = [
            "schtasks",
            "/create",
            "/tn",
            self.TASK_NAME,
            "/tr",
            self._command(),
            "/sc",
            "daily",
            "/st",
            time_str,
            "/f",
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
            return {
                "status": "success",
                "message": f"Scheduled task created for {time_str} daily.",
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Failed to create scheduled task: {e.stderr}",
            }

    def _disable_windows(self) -> dict[str, Any]:
        command = ["schtasks", "/delete", "/tn", self.TASK_NAME, "/f"]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
            return {"status": "success", "message": "Scheduled task removed."}
        except subprocess.CalledProcessError as e:
            if "not found" in e.stderr.lower():
                return {
                    "status": "success",
                    "message": "No scheduled task found to remove.",
                }
            return {"status": "error", "message": f"Failed to remove task: {e.stderr}"}

    def _status_windows(self) -> dict[str, Any]:
        command = ["schtasks", "/query", "/tn", self.TASK_NAME, "/fo", "LIST"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return {
                "enabled": True,
                "details": result.stdout,
                "message": "Scheduled job is ENABLED.",
            }
        except subprocess.CalledProcessError:
            return {
                "enabled": False,
                "message": "Scheduled job is DISABLED.",
            }

    # Unix/OSX (crontab)

    def _enable_unix(self, time_str: str = "23:55") -> dict[str, Any]:
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            hour, minute = 23, 55

        marker = f"# {self.TASK_NAME}"
        cron_entry = f"{minute} {hour} * * * {self._command()}  {marker}"

        try:
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout
            lines = [line for line in current_cron.splitlines() if marker not in line]
            new_cron = "\n".join(lines).rstrip() + "\n" + cron_entry + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
            return {
                "status": "success",
                "message": f"Crontab entry added for {time_str} daily.",
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to update crontab: {str(e)}"}

    def _disable_unix(self) -> dict[str, Any]:
        marker = f"# {self.TASK_NAME}"
        try:
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout
            lines = current_cron.splitlines()
            new_lines = [line for line in lines if marker not in line]
            if len(new_lines) == len(lines):
                return {"status": "success", "message": "No schedule found."}
            new_cron = "\n".join(new_lines) + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
            return {"status": "success", "message": "Crontab entry removed."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to disable: {str(e)}"}

    def _status_unix(self) -> dict[str, Any]:
        marker = f"# {self.TASK_NAME}"
        try:
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout
            if marker in current_cron:
                return {
                    "enabled": True,
                    "message": "Scheduled job is ENABLED (cron).",
                }
            return {
                "enabled": False,
                "message": "Scheduled job is DISABLED.",
            }
        except Exception:
            return {
                "enabled": False,
                "message": "Scheduled job is DISABLED.",
            }
