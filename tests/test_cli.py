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

from memanto.app.clients.backend import Backend
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
    "memanto.cli.commands.migrate",
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
            mock_cfg.get_backend.return_value = Backend.CLOUD
            mock_cfg.get_onprem_config.return_value = {
                "url": "http://localhost:8080",
                "embedding_provider": "",
            }
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

    def test_remember_short_content_honors_custom_title(self, mock_all_clients):
        """Short memories should still use an explicit --title."""
        mock_all_clients.remember.return_value = {
            "memory_id": "mem-123",
            "status": "queued",
        }

        result = runner.invoke(
            app, ["remember", "Short memory", "--title", "Custom Title"]
        )

        assert result.exit_code == 0
        mock_all_clients.remember.assert_called_once()
        assert mock_all_clients.remember.call_args.kwargs["title"] == "Custom Title"

    def test_edit(self, mock_all_clients):
        """Test 'memanto edit' updates selected memory fields."""
        mock_all_clients.update_memory.return_value = {
            "memory_id": "mem-123",
            "status": "success",
            "updated_fields": ["title", "tags"],
        }

        result = runner.invoke(
            app,
            [
                "edit",
                "mem-123",
                "--title",
                "Updated title",
                "--tags",
                "alpha,beta",
            ],
        )

        assert result.exit_code == 0
        assert "updated successfully" in result.stdout.lower()
        mock_all_clients.update_memory.assert_called_once_with(
            agent_id="test-agent",
            memory_id="mem-123",
            updates={"title": "Updated title", "tags": ["alpha", "beta"]},
        )

    def test_edit_requires_field(self, mock_all_clients):
        """Test 'memanto edit' rejects an empty update."""
        result = runner.invoke(app, ["edit", "mem-123"])

        assert result.exit_code != 0
        assert "No update fields provided" in result.stdout
        mock_all_clients.update_memory.assert_not_called()

    def test_edit_normalizes_string_confidence_to_float(self, mock_all_clients):
        """String `confidence` values like '0.7' must be coerced to float
        before reaching the write service. CodeRabbit review
        2026-06-14T14:03:20Z on PR #633 flagged the direct-client path
        forwarded the raw string.

        Asserts the value forwarded to `update_memory` is a numeric `float`,
        not the original `"0.7"` string.
        """
        from unittest.mock import MagicMock, patch

        from memanto.cli.client.direct_client import DirectClient

        mock_write_service = MagicMock()
        mock_write_service.update_memory.return_value = {
            "memory_id": "mem-123",
            "status": "updated",
            "action": "updated",
            "updated_fields": ["confidence"],
        }
        mock_session = MagicMock()
        mock_session.namespace = "memanto_agent_test-agent"
        mock_session.session_token = "test-token"

        with (
            patch.object(
                DirectClient, "_get_write_service", return_value=mock_write_service
            ),
            patch.object(
                DirectClient,
                "_get_validated_session_for_agent",
                return_value=mock_session,
            ),
        ):
            client = DirectClient.__new__(DirectClient)
            client.api_key = "test-api-key"
            client.base_url = "https://api.moorcheh.ai/v1"
            result = client.update_memory(
                agent_id="test-agent",
                memory_id="mem-123",
                updates={"confidence": "0.7"},
            )

        # update_memory(memory_id, namespace, updates) is called positionally
        forwarded_updates = mock_write_service.update_memory.call_args.args[2]
        forwarded_confidence = forwarded_updates["confidence"]
        assert isinstance(forwarded_confidence, float)
        assert forwarded_confidence == 0.7
        assert result["status"] == "updated"

    def test_edit_rejects_invalid_confidence_string(self, mock_all_clients):
        """Non-numeric string confidence like 'high' must be rejected on
        the direct-client path (same contract as the API route)."""
        from unittest.mock import MagicMock, patch

        from memanto.cli.client.direct_client import DirectClient

        mock_write_service = MagicMock()
        mock_session = MagicMock()
        mock_session.namespace = "memanto_agent_test-agent"

        with (
            patch.object(
                DirectClient, "_get_write_service", return_value=mock_write_service
            ),
            patch.object(
                DirectClient,
                "_get_validated_session_for_agent",
                return_value=mock_session,
            ),
        ):
            client = DirectClient.__new__(DirectClient)
            client.api_key = "test-api-key"
            client.base_url = "https://api.moorcheh.ai/v1"
            import pytest

            with pytest.raises(ValueError, match="Confidence must be a number"):
                client.update_memory(
                    agent_id="test-agent",
                    memory_id="mem-123",
                    updates={"confidence": "high"},
                )

        mock_write_service.update_memory.assert_not_called()

    def test_edit_sdk_rejects_unknown_field(self, mock_all_clients):
        """SdkClient.update_memory must enforce the same field allowlist as
        the API route. CodeRabbit review 2026-06-14T14:03:20Z flagged that
        the SDK path forwarded unknown fields straight to the write service."""
        from unittest.mock import MagicMock, patch

        from memanto.cli.client.sdk_client import SdkClient

        mock_write_service = MagicMock()
        mock_session = MagicMock()
        mock_session.namespace = "memanto_agent_test-agent"

        with (
            patch.object(
                SdkClient, "_get_write_service", return_value=mock_write_service
            ),
            patch.object(
                SdkClient, "_get_validated_session_for_agent", return_value=mock_session
            ),
        ):
            client = SdkClient.__new__(SdkClient)
            client.api_key = "test-api-key"
            import pytest

            with pytest.raises(ValueError, match="Unknown update field"):
                client.update_memory(
                    agent_id="test-agent",
                    memory_id="mem-123",
                    updates={"malicious_field": "x"},
                )

        mock_write_service.update_memory.assert_not_called()

    def test_edit_sdk_rejects_blank_content(self, mock_all_clients):
        """SdkClient.update_memory must reject blank content strings."""
        from unittest.mock import MagicMock, patch

        from memanto.cli.client.sdk_client import SdkClient

        mock_write_service = MagicMock()
        mock_session = MagicMock()
        mock_session.namespace = "memanto_agent_test-agent"

        with (
            patch.object(
                SdkClient, "_get_write_service", return_value=mock_write_service
            ),
            patch.object(
                SdkClient, "_get_validated_session_for_agent", return_value=mock_session
            ),
        ):
            client = SdkClient.__new__(SdkClient)
            client.api_key = "test-api-key"
            import pytest

            with pytest.raises(ValueError, match="non-empty string"):
                client.update_memory(
                    agent_id="test-agent",
                    memory_id="mem-123",
                    updates={"content": "   "},
                )

        mock_write_service.update_memory.assert_not_called()

    def test_edit_sdk_normalizes_confidence_and_accepts_valid_payload(
        self, mock_all_clients
    ):
        """SdkClient.update_memory must coerce string confidence and accept
        the full valid payload set, matching the API route contract."""
        from unittest.mock import MagicMock, patch

        from memanto.cli.client.sdk_client import SdkClient

        mock_write_service = MagicMock()
        mock_write_service.update_memory.return_value = {
            "memory_id": "mem-123",
            "status": "updated",
            "action": "updated",
            "updated_fields": ["confidence", "tags"],
        }
        mock_session = MagicMock()
        mock_session.namespace = "memanto_agent_test-agent"

        with (
            patch.object(
                SdkClient, "_get_write_service", return_value=mock_write_service
            ),
            patch.object(
                SdkClient, "_get_validated_session_for_agent", return_value=mock_session
            ),
        ):
            client = SdkClient.__new__(SdkClient)
            client.api_key = "test-api-key"
            result = client.update_memory(
                agent_id="test-agent",
                memory_id="mem-123",
                updates={"confidence": "0.5", "tags": ["a", "b"]},
            )

        call_args = mock_write_service.update_memory.call_args
        # update_memory(memory_id, namespace, updates) is called positionally
        forwarded_updates = (
            call_args.args[2]
            if len(call_args.args) > 2
            else call_args.kwargs.get("updates")
        )
        assert isinstance(forwarded_updates["confidence"], float)
        assert forwarded_updates["confidence"] == 0.5
        assert forwarded_updates["tags"] == ["a", "b"]
        assert result["status"] == "updated"

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

    def test_recall_recent(self, mock_all_clients):
        """`memanto recall --recent` lists newest memories chronologically."""
        mock_all_clients.recall_recent.return_value = {
            "memories": [
                {"content": "Newest memory", "score": 0.0, "type": "fact"},
                {"content": "Older memory", "score": 0.0, "type": "preference"},
            ],
            "count": 2,
        }

        result = runner.invoke(app, ["recall", "--recent", "--limit", "5"])
        assert result.exit_code == 0
        assert "Recent (newest first)" in result.stdout
        assert "Newest memory" in result.stdout
        mock_all_clients.recall_recent.assert_called_once()
        call_kwargs = mock_all_clients.recall_recent.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_recall_recent_rejects_query(self, mock_all_clients):
        """`--recent` is chronological; passing a query alongside is an error."""
        result = runner.invoke(app, ["recall", "some query", "--recent"])
        assert result.exit_code != 0
        assert "Cannot provide a search query" in result.stdout

    def test_recall_rejects_multiple_temporal_flags(self, mock_all_clients):
        """`--recent` and `--as-of` are mutually exclusive."""
        result = runner.invoke(app, ["recall", "--recent", "--as-of", "2025-11-01"])
        assert result.exit_code != 0
        assert "multiple temporal query modes" in result.stdout

    def test_forget_force(self, mock_all_clients):
        """Test 'memanto forget --force' deletes a memory without prompting."""
        mock_all_clients.delete_memory.return_value = {
            "status": "deleted",
            "agent_id": "test-agent",
            "memory_id": "mem-123",
        }

        result = runner.invoke(app, ["forget", "mem-123", "--force"])

        assert result.exit_code == 0
        assert "deleted successfully" in result.stdout.lower()
        assert "mem-123" in result.stdout
        mock_all_clients.delete_memory.assert_called_once_with(
            agent_id="test-agent", memory_id="mem-123"
        )

    def test_forget_cancelled(self, mock_all_clients):
        """Test 'memanto forget' respects a negative confirmation."""
        result = runner.invoke(app, ["forget", "mem-123"], input="n\n")

        assert result.exit_code == 0
        assert "cancelled" in result.stdout.lower()
        mock_all_clients.delete_memory.assert_not_called()

    def test_forget_not_found(self, mock_all_clients):
        """Test 'memanto forget' shows a clear client error."""
        mock_all_clients.delete_memory.side_effect = Exception("Memory not found")

        result = runner.invoke(app, ["forget", "missing-memory", "--force"])

        assert result.exit_code != 0
        assert "Memory not found" in result.stdout

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

    def test_remember_from_conversation_dry_run(self, mock_all_clients, tmp_path):
        """Test 'memanto remember --from-conversation --dry-run'"""
        conversation_file = tmp_path / "messages.json"
        conversation_file.write_text(
            json.dumps(
                [
                    {"role": "user", "content": "I prefer short PR summaries."},
                    {"role": "assistant", "content": "I will remember that."},
                ]
            )
        )
        mock_all_clients.extract_memories_from_conversation.return_value = {
            "dry_run": True,
            "candidates": [
                {
                    "type": "preference",
                    "title": "PR summary preference",
                    "content": "The user prefers short PR summaries.",
                    "confidence": 0.9,
                }
            ],
            "count": 1,
        }

        result = runner.invoke(
            app,
            ["remember", "--from-conversation", str(conversation_file), "--dry-run"],
        )

        assert result.exit_code == 0
        assert "Dry run" in result.stdout
        assert "PR summary preference" in result.stdout
        mock_all_clients.extract_memories_from_conversation.assert_called_once()
        call_kwargs = (
            mock_all_clients.extract_memories_from_conversation.call_args.kwargs
        )
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["messages"][0]["role"] == "user"

    def test_remember_from_conversation_stores_extracted_memories(
        self, mock_all_clients, tmp_path
    ):
        """Conversation extraction stores candidates when dry-run is not used."""
        conversation_file = tmp_path / "messages.json"
        conversation_file.write_text(
            json.dumps([{"role": "user", "content": "The project uses pytest."}])
        )
        mock_all_clients.extract_memories_from_conversation.return_value = {
            "dry_run": False,
            "successful": 1,
            "total_submitted": 1,
            "failed": 0,
            "candidates": [
                {
                    "type": "fact",
                    "title": "Test framework",
                    "content": "The project uses pytest.",
                    "confidence": 0.85,
                }
            ],
        }

        result = runner.invoke(
            app,
            ["remember", "--from-conversation", str(conversation_file)],
        )

        assert result.exit_code == 0
        assert "Stored 1/1 extracted memories" in result.stdout
        mock_all_clients.extract_memories_from_conversation.assert_called_once()

    def test_remember_from_conversation_rejects_batch_combo(
        self, mock_all_clients, tmp_path
    ):
        """Conversation extraction is mutually exclusive with batch mode."""
        conversation_file = tmp_path / "messages.json"
        conversation_file.write_text(json.dumps([{"role": "user", "content": "x"}]))

        result = runner.invoke(
            app,
            [
                "remember",
                "--from-conversation",
                str(conversation_file),
                "--batch",
                str(conversation_file),
            ],
        )

        assert result.exit_code != 0
        assert "cannot be combined" in result.stdout

    def test_daily_summary(self, mock_all_clients):
        """Test 'memanto daily-summary' (summary only — no conflicts)."""
        mock_all_clients.generate_daily_summary.return_value = {
            "summary": {"status": "success", "summary_path": "summary.md"},
        }
        result = runner.invoke(app, ["daily-summary"])
        assert result.exit_code == 0
        assert "generated" in result.stdout.lower()

    def test_detect_conflicts(self, mock_all_clients):
        """Test 'memanto detect-conflicts'"""
        mock_all_clients.generate_conflict_report.return_value = {
            "conflicts": {
                "status": "success",
                "conflict_count": 0,
                "json_path": "conflicts.json",
            },
        }
        result = runner.invoke(app, ["detect-conflicts"])
        assert result.exit_code == 0
        assert "conflict report generated" in result.stdout.lower()

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

    def test_migrate_help(self):
        """Test 'memanto migrate --help'"""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "supermemory" in result.stdout.lower()
        assert "mem0" in result.stdout.lower()
        assert "letta" in result.stdout.lower()

    def _write_export_file(self, tmp_path, name, export):
        """Helper: dump an export dict to JSON so migrate can load it via --file."""
        path = tmp_path / name
        path.write_text(json.dumps(export), encoding="utf-8")
        return path

    def test_migrate_supermemory_dry_run(self, mock_all_clients, tmp_path):
        """'memanto migrate supermemory --file ... --dry-run' renders a savings report."""
        export = {
            "exported_at": "2026-06-04T00:00:00Z",
            "summary": {
                "document_count": 2,
                "chunk_count": 5,
                "memory_entry_count": 1,
                "container_tag_count": 1,
                "connection_count": 0,
            },
            "documents": [],
            "memories": [
                {"id": "m1", "content": "team uses Python", "container_tag": "eng"},
            ],
        }
        export_file = self._write_export_file(
            tmp_path, "supermemory_export.json", export
        )

        # Moorcheh answer endpoint returns a markdown narrative for the report.
        mock_all_clients.answer.return_value = {
            "answer": "## Executive summary\nMigrating saves tokens.",
        }

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "test-token")
            mock_cfg.get_answer_config.return_value = {
                "model": "anthropic.claude-sonnet-4-6"
            }

            result = runner.invoke(
                app,
                ["migrate", "supermemory", "--file", str(export_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout

        reports = list(tmp_path.glob("*/migrate-report.md"))
        assert len(reports) == 1
        report_text = reports[0].read_text(encoding="utf-8")
        assert "Memanto vs. Supermemory" in report_text
        assert "Executive summary" in report_text
        assert "Method & assumptions" in report_text

    def test_migrate_mem0_dry_run(self, mock_all_clients, tmp_path):
        """'memanto migrate mem0 --file ... --dry-run' maps and renders a report."""
        export = {
            "exported_at": "2026-06-04T00:00:00Z",
            "summary": {
                "entity_count": 2,
                "scope_count": 2,
                "memory_count": 2,
            },
            "entities": [
                {"id": "user:alice", "name": "alice", "type": "user"},
                {"id": "agent:bot", "name": "bot", "type": "agent"},
            ],
            "memories": [
                {"id": "m1", "memory": "User prefers dark mode"},
                {"id": "m2", "memory": "Timezone is PST"},
            ],
        }
        export_file = self._write_export_file(tmp_path, "mem0_export.json", export)

        mock_all_clients.answer.return_value = {
            "answer": "## Executive summary\nMigrating from Mem0 saves tokens.",
        }

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "test-token")
            mock_cfg.get_answer_config.return_value = {
                "model": "anthropic.claude-sonnet-4-6"
            }

            result = runner.invoke(
                app,
                ["migrate", "mem0", "--file", str(export_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout

        reports = list(tmp_path.glob("*/migrate-report.md"))
        assert len(reports) == 1
        report_text = reports[0].read_text(encoding="utf-8")
        assert "Memanto vs. Mem0" in report_text
        assert "Executive summary" in report_text
        assert "Method & assumptions" in report_text

    def test_migrate_letta_dry_run(self, mock_all_clients, tmp_path):
        """'memanto migrate letta --file ... --dry-run' maps and renders a report."""
        export = {
            "exported_at": "2026-06-04T00:00:00Z",
            "export_mode": "all_agents",
            "summary": {
                "agent_count": 2,
                "passage_count": 2,
                "passage_pages": 2,
            },
            "agents": [
                {"id": "agent-test-123", "name": "lette"},
                {"id": "agent-test-456", "name": "support-bot"},
            ],
            "passages": [
                {"id": "p1", "text": "User prefers dark mode"},
                {"id": "p2", "text": "Timezone is PST"},
            ],
        }
        export_file = self._write_export_file(tmp_path, "letta_export.json", export)

        mock_all_clients.answer.return_value = {
            "answer": "## Executive summary\nMigrating from Letta saves tokens.",
        }

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "test-token")
            mock_cfg.get_answer_config.return_value = {
                "model": "anthropic.claude-sonnet-4-6"
            }

            result = runner.invoke(
                app,
                ["migrate", "letta", "--file", str(export_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout

        reports = list(tmp_path.glob("*/migrate-report.md"))
        assert len(reports) == 1
        report_text = reports[0].read_text(encoding="utf-8")
        assert "Memanto vs. Letta" in report_text
        assert "Executive summary" in report_text
        assert "Method & assumptions" in report_text

    def test_migrate_narrative_retries_on_invalid_session(
        self, mock_all_clients, tmp_path
    ):
        """Migrate re-activates the agent when the Moorcheh session token is invalid."""
        from memanto.app.utils.errors import InvalidSessionTokenError

        export = {
            "exported_at": "2026-06-04T00:00:00Z",
            "export_mode": "all_agents",
            "summary": {"agent_count": 1, "passage_count": 1},
            "agents": [{"id": "agent-1", "name": "lette"}],
            "passages": [{"id": "p1", "text": "hello"}],
        }
        export_file = self._write_export_file(tmp_path, "letta_export.json", export)

        mock_all_clients.answer.side_effect = [
            InvalidSessionTokenError(
                "Invalid session token: Signature verification failed"
            ),
            {"answer": "## Executive summary\nRecovered after re-activation."},
        ]
        mock_all_clients.activate_agent.return_value = {
            "agent_id": "test-agent",
            "session_token": "new-token",
        }

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "stale-token")
            mock_cfg.get_answer_config.return_value = {
                "model": "anthropic.claude-sonnet-4-6"
            }

            result = runner.invoke(
                app,
                ["migrate", "letta", "--file", str(export_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        mock_all_clients.activate_agent.assert_called_once_with("test-agent")
        assert mock_all_clients.answer.call_count == 2

        reports = list(tmp_path.glob("*/migrate-report.md"))
        report_text = reports[0].read_text(encoding="utf-8")
        assert "Recovered after re-activation." in report_text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
