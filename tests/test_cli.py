#!/usr/bin/env python3
"""
MEMANTO CLI Integration Tests

Tests all major CLI commands using typer.testing.CliRunner.
Uses extensive mocking to intercept API calls across all command modules.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from memanto.cli.main import app

runner = CliRunner()

# Modules that import get_client and need to be patched
COMMAND_MODULES = [
    "memanto.cli.commands._shared",
    "memanto.cli.commands.agent",
    "memanto.cli.commands.memory",
    "memanto.cli.commands.session",
    "memanto.cli.commands.core",
    "memanto.cli.commands.config_cmd",
    "memanto.cli.commands.connect",
    "memanto.cli.commands.memory_mgmt",
    "memanto.cli.commands.schedule",
]


@pytest.fixture(autouse=True)
def mock_all_clients():
    """Mock get_client for all command modules to ensure it's intercepted everywhere"""
    client = MagicMock()

    # Standard mocks for common client attributes
    client.agent_id = "test-agent"
    client.session_token = "test-token"

    patches = []
    # Patch get_client and config_manager independently — not every command
    # module imports both, and a missing attribute on one must not skip the
    # other (which previously left config_manager unmocked in modules like
    # `session.py` that only use config_manager).
    for module in COMMAND_MODULES:
        try:
            p = patch(f"{module}.get_client", return_value=client)
            p.start()
            patches.append(p)
        except (ImportError, AttributeError):
            pass

        try:
            p_cfg = patch(f"{module}.config_manager")
            mock_cfg = p_cfg.start()
            mock_cfg.get_api_key.return_value = "test-api-key"
            mock_cfg.get_active_session.return_value = ("test-agent", "test-token")
            mock_cfg.get_server_config.return_value = {
                "url": "localhost",
                "port": 8000,
                "auto_start": False,
            }
            mock_cfg.get_session_config.return_value = {
                "default_duration_hours": 6,
                "auto_renew_enabled": True,
            }
            mock_cfg.get_cli_config.return_value = {
                "interactive_mode": True,
                "smart_parse": True,
            }
            mock_cfg.get_answer_config.return_value = {
                "model": "anthropic.claude-sonnet-4-6",
                "temperature": 0.7,
                "answer_limit": 15,
                "threshold": 0.01,
            }
            mock_cfg.get_recall_config.return_value = {"limit": 10}
            mock_cfg.get_schedule_time.return_value = "23:55"
            mock_cfg.config_dir = "/tmp/.memanto"
            patches.append(p_cfg)
        except (ImportError, AttributeError):
            pass

    # Specialized patches for connect module utilities
    p_la = patch("memanto.cli.commands.connect.list_agents", return_value=[])
    p_la.start()
    patches.append(p_la)

    p_da = patch(
        "memanto.cli.commands.connect.detect_agents_in_project", return_value=[]
    )
    p_da.start()
    patches.append(p_da)

    p_mi = patch(
        "memanto.cli.commands.connect.detect_memanto_installed", return_value=[]
    )
    p_mi.start()
    patches.append(p_mi)

    p_mig = patch(
        "memanto.cli.commands.connect.detect_memanto_installed_global", return_value=[]
    )
    p_mig.start()
    patches.append(p_mig)

    yield client

    for p in patches:
        p.stop()


class TestMEMANTOCLI:
    """Integration tests for MEMANTO CLI commands"""

    def test_base_command_help(self):
        """Test 'memanto --help'"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Memory that AI Agents Love!" in result.stdout

    def test_status_command(self, mock_all_clients):
        """Test 'memanto status'"""
        # Status command might use helper functions, let's just check it runs
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "MEMANTO Status" in result.stdout

    # ========================================================================
    # AGENT COMMANDS
    # ========================================================================

    def test_agent_create(self, mock_all_clients):
        """Test 'memanto agent create'"""
        mock_all_clients.create_agent.return_value = {
            "agent_id": "test-agent",
            "namespace": "memanto_agent_test-agent",
        }
        mock_all_clients.activate_agent.return_value = {
            "session_id": "sess-test",
            "session_token": "test-token",
            "agent_id": "test-agent",
            "expires_at": "2026-03-19T20:00:00Z",
        }

        result = runner.invoke(
            app, ["agent", "create", "test-agent", "--pattern", "support"]
        )
        if result.exit_code != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"EXCEPTION: {result.exception}")

        assert result.exit_code == 0
        assert "test-agent" in result.stdout
        assert "created successfully" in result.stdout.lower()
        assert "agent activated automatically" in result.stdout.lower()
        mock_all_clients.activate_agent.assert_called_once_with("test-agent", 6)

    def test_agent_list(self, mock_all_clients):
        """Test 'memanto agent list'"""
        mock_all_clients.list_agents.return_value = [
            {"agent_id": "agent-1", "pattern": "support", "description": "Desc 1"},
            {"agent_id": "agent-2", "pattern": "tool", "description": "Desc 2"},
        ]

        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "agent-1" in result.stdout
        assert "agent-2" in result.stdout

    def test_agent_activate(self, mock_all_clients):
        """Test 'memanto agent activate'"""
        mock_all_clients.activate_agent.return_value = {
            "session_id": "test-session",
            "session_token": "test-token",
            "agent_id": "test-agent",
            "expires_at": "2026-03-19T20:00:00Z",
        }

        result = runner.invoke(app, ["agent", "activate", "test-agent"])
        assert result.exit_code == 0
        assert "test-agent" in result.stdout
        assert "activated" in result.stdout.lower()

    # ========================================================================
    # MEMORY OPERATIONS
    # ========================================================================

    def test_remember(self, mock_all_clients):
        """Test 'memanto remember'"""
        mock_all_clients.remember.return_value = {
            "memory_id": "mem-123",
            "status": "queued",
        }

        result = runner.invoke(
            app, ["remember", "Test memory content", "--title", "Test Title"]
        )
        assert result.exit_code == 0
        assert "stored successfully" in result.stdout.lower()
        assert "mem-123" in result.stdout

    def test_recall(self, mock_all_clients):
        """Test 'memanto recall'"""
        mock_all_clients.recall.return_value = {
            "memories": [
                {"content": "Found memory 1", "score": 0.9, "type": "fact"},
                {"content": "Found memory 2", "score": 0.8, "type": "fact"},
            ],
            "count": 2,
        }

        result = runner.invoke(app, ["recall", "test query"])
        assert result.exit_code == 0
        assert "Found 2 memories" in result.stdout
        assert "Found memory 1" in result.stdout

    def test_answer(self, mock_all_clients):
        """Test 'memanto answer'"""
        mock_all_clients.answer.return_value = {
            "answer": "This is the RAG answer.",
            "sources": ["source-1"],
        }

        result = runner.invoke(app, ["answer", "What is the answer?"])
        assert result.exit_code == 0
        assert "This is the RAG answer" in result.stdout

    # ========================================================================
    # SESSION COMMANDS
    # ========================================================================

    def test_session_info(self, mock_all_clients):
        """Test 'memanto session info'"""
        mock_all_clients.get_session_info.return_value = {
            "agent_id": "test-agent",
            "status": "active",
            "time_remaining_seconds": 3600,
            "session_id": "test-session",
            "namespace": "memanto_agent_test-agent",
            "pattern": "support",
            "started_at": "2026-03-19T14:00:00Z",
            "expires_at": "2026-03-19T15:00:00Z",
        }

        result = runner.invoke(app, ["session", "info"])
        assert result.exit_code == 0
        assert "Active Agent" in result.stdout
        assert "Session Token" in result.stdout

    def test_agent_deactivate(self, mock_all_clients):
        """Test 'memanto agent deactivate'"""
        result = runner.invoke(app, ["agent", "deactivate"])
        assert result.exit_code == 0
        assert "deactivated" in result.stdout.lower()

    def test_agent_delete_keep_cloud(self, mock_all_clients):
        """Test 'memanto agent delete --force' keeping cloud memories (default)"""
        mock_all_clients.delete_agent.return_value = {
            "status": "deleted",
            "agent_id": "test-agent",
        }

        # Answer "y" to keep cloud memories (default)
        result = runner.invoke(
            app, ["agent", "delete", "test-agent", "--force"], input="y\n"
        )
        assert result.exit_code == 0
        assert "deleted" in result.stdout.lower()
        mock_all_clients.delete_agent.assert_called_once_with("test-agent")
        mock_all_clients._get_moorcheh.return_value.namespaces.delete.assert_not_called()

    def test_agent_delete_purge_cloud(self, mock_all_clients):
        """Test 'memanto agent delete --force' also deleting cloud namespace"""
        mock_all_clients.delete_agent.return_value = {
            "status": "deleted",
            "agent_id": "test-agent",
        }
        mock_moorcheh = MagicMock()
        mock_all_clients._get_moorcheh.return_value = mock_moorcheh

        # Answer "n" to delete cloud memories too
        result = runner.invoke(
            app, ["agent", "delete", "test-agent", "--force"], input="n\n"
        )
        assert result.exit_code == 0
        assert "deleted" in result.stdout.lower()
        mock_moorcheh.namespaces.delete.assert_called_once_with(
            "memanto_agent_test-agent"
        )

    def test_agent_delete_not_found(self, mock_all_clients):
        """Test 'memanto agent delete' when agent does not exist"""
        mock_all_clients.delete_agent.side_effect = Exception("Agent not found")

        result = runner.invoke(
            app, ["agent", "delete", "ghost-agent", "--force"], input="y\n"
        )
        assert result.exit_code != 0
        assert "ghost-agent" in result.stdout

    def test_agent_bootstrap(self, mock_all_clients):
        """Test 'memanto agent bootstrap'"""
        mock_all_clients.get_agent.return_value = {
            "agent_id": "test-agent",
            "pattern": "support",
            "namespace": "memanto_agent_test-agent",
        }
        mock_all_clients.recall.return_value = {"memories": []}

        result = runner.invoke(app, ["agent", "bootstrap"])
        assert result.exit_code == 0
        assert "Intelligence Snapshot" in result.stdout

    def test_memory_batch_remember(self, mock_all_clients, tmp_path):
        """Test 'memanto remember --batch'"""
        batch_file = tmp_path / "batch.json"
        batch_data = [{"content": "Batch memory 1"}, {"content": "Batch memory 2"}]
        batch_file.write_text(json.dumps(batch_data))

        mock_all_clients.batch_remember.return_value = {
            "successful": 2,
            "total_submitted": 2,
            "failed": 0,
        }

        result = runner.invoke(app, ["remember", "--batch", str(batch_file)])
        assert result.exit_code == 0
        assert "Stored 2/2 memories successfully" in result.stdout

    def test_daily_summary(self, mock_all_clients):
        """Test 'memanto daily-summary'"""
        mock_all_clients.generate_daily_summary.return_value = {
            "summary": {"status": "success", "summary_path": "summary.md"},
            "conflicts": {
                "status": "success",
                "conflict_count": 0,
                "json_path": "conflicts.json",
            },
        }
        result = runner.invoke(app, ["daily-summary"])
        assert result.exit_code == 0
        assert "generated" in result.stdout.lower()

    def test_conflicts_list(self, mock_all_clients):
        """Test 'memanto conflicts --list'"""
        # Patch Path.home to avoid real file checks if possible or just mock the logic
        mock_all_clients.list_conflicts.return_value = [
            {
                "title": "Conflict 1",
                "old_content": "A",
                "new_content": "B",
                "recommendation": "merge",
            }
        ]
        result = runner.invoke(app, ["conflicts", "--list"])
        assert result.exit_code == 0
        assert "Found 1 unresolved conflict" in result.stdout

    def test_memory_export(self, mock_all_clients):
        """Test 'memanto memory export'"""
        mock_all_clients.export_memory_md.return_value = {
            "total_memories": 5,
            "output_path": "memory.md",
        }
        result = runner.invoke(app, ["memory", "export"])
        assert result.exit_code == 0
        assert "Exported 5 memories" in result.stdout

    def test_memory_sync(self, mock_all_clients):
        """Test 'memanto memory sync'"""
        mock_all_clients.sync_memory_to_project.return_value = {
            "total_memories": 5,
            "source": "cache",
            "output_path": "project/memory.md",
        }
        result = runner.invoke(app, ["memory", "sync"])
        assert result.exit_code == 0
        assert "Synced 5 memories" in result.stdout

    def test_schedule_commands(self, mock_all_clients):
        """Test schedule commands"""
        with patch("memanto.cli.commands.schedule.ScheduleManager") as mock_manager_cls:
            mock_manager = mock_manager_cls.return_value
            mock_manager.enable.return_value = {
                "status": "success",
                "message": "Enabled",
            }
            mock_manager.disable.return_value = {
                "status": "success",
                "message": "Disabled",
            }
            mock_manager.get_status.return_value = {
                "enabled": True,
                "python_exe": "python",
            }

            # Test enable
            result = runner.invoke(app, ["schedule", "enable"])
            assert result.exit_code == 0
            assert "Enabled" in result.stdout

            # Test disable
            result = runner.invoke(app, ["schedule", "disable"])
            assert result.exit_code == 0
            assert "Disabled" in result.stdout

            # Test status
            result = runner.invoke(app, ["schedule", "status"])
            assert result.exit_code == 0
            assert "ENABLED" in result.stdout

    def test_config_show(self, mock_all_clients):
        """Test 'memanto config show'"""
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "MEMANTO Configuration" in result.stdout

    def test_connect_list(self, mock_all_clients):
        """Test 'memanto connect list'"""
        result = runner.invoke(app, ["connect", "list"])
        assert result.exit_code == 0
        assert "MEMANTO Agent Integrations" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
