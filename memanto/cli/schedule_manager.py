"""
Schedule Manager for MEMANTO
Handles OS-level scheduling for daily summaries.
"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


class ScheduleManager:
    """Manages OS-level scheduled tasks for MEMANTO"""

    TASK_NAME = "MemantoDailySummary"

    def __init__(self):
        self.os_type = platform.system()
        # Find the absolute path to cli/main.py
        # Assuming this file is in cli/schedule_manager.py
        self.cli_main = Path(__file__).parent / "main.py"
        self.python_exe = sys.executable

    def enable(self, time_str: str = "23:55") -> dict[str, Any]:
        """Enable daily scheduling at the given HH:MM time."""
        if self.os_type == "Windows":
            return self._enable_windows(time_str)
        return self._enable_unix(time_str)

    def disable(self) -> dict[str, Any]:
        """Disable daily scheduling"""
        if self.os_type == "Windows":
            return self._disable_windows()
        return self._disable_unix()

    def get_status(self) -> dict[str, Any]:
        """Check if scheduling is enabled"""
        if self.os_type == "Windows":
            return self._status_windows()
        return self._status_unix()

    # Windows Implementation (schtasks)

    def _enable_windows(self, time_str: str = "23:55") -> dict[str, Any]:
        # Command to run: python <main_path> daily-summary
        # We use absolute paths to avoid issues with working directories
        cmd_to_run = f'"{self.python_exe}" "{self.cli_main.absolute()}" daily-summary'

        # schtasks command
        # /sc daily: schedule daily
        # /st HH:MM: start time (configurable)
        # /f: force creation (overwrite if exists)
        command = [
            "schtasks",
            "/create",
            "/tn",
            self.TASK_NAME,
            "/tr",
            cmd_to_run,
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
            # If it doesn't exist, that's fine too
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
                "message": "Daily summary scheduling is ENABLED.",
            }
        except subprocess.CalledProcessError:
            return {
                "enabled": False,
                "message": "Daily summary scheduling is DISABLED.",
            }

    # Unix/OSX Implementation (crontab)

    def _enable_unix(self, time_str: str = "23:55") -> dict[str, Any]:
        # Parse HH:MM
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            hour, minute = 23, 55

        cron_entry = f'{minute} {hour} * * * "{self.python_exe}" "{self.cli_main.absolute()}" daily-summary'

        try:
            # Get current crontab
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout

            # Remove existing MEMANTO entry if any
            lines = current_cron.splitlines()
            lines = [line for line in lines if "daily-summary" not in line]

            # Add new entry
            new_cron = "\n".join(lines).rstrip() + "\n" + cron_entry + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)

            return {
                "status": "success",
                "message": f"Crontab entry added for {time_str} daily.",
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to update crontab: {e!s}"}

    def _disable_unix(self) -> dict[str, Any]:
        try:
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout
            lines = current_cron.splitlines()

            # Filter out our entry
            new_lines = [
                line
                for line in lines
                if f"{self.TASK_NAME}" not in line and "daily-summary" not in line
            ]

            if len(new_lines) == len(lines):
                return {"status": "success", "message": "No schedule found."}

            new_cron = "\n".join(new_lines) + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
            return {"status": "success", "message": "Crontab entry removed."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to disable: {e!s}"}

    def _status_unix(self) -> dict[str, Any]:
        try:
            current_cron = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True
            ).stdout
            if "daily-summary" in current_cron:
                return {
                    "enabled": True,
                    "message": "Daily summary scheduling is ENABLED (cron).",
                }
            return {
                "enabled": False,
                "message": "Daily summary scheduling is DISABLED.",
            }
        except Exception:
            return {
                "enabled": False,
                "message": "Daily summary scheduling is DISABLED.",
            }
