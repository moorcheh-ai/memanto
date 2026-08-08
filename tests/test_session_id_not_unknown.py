"""
Test: session_id must be the real session ID, not hardcoded "unknown".

Regression test for the bug where DirectClient.remember() and
DirectClient.batch_remember() logged session summaries with
session_id="unknown" instead of the actual session.session_id,
breaking session traceability in local Markdown logs.

Refs: #770
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_session(sid="sess_test123"):
    s = MagicMock()
    s.session_id = sid
    s.agent_id = "agent-1"
    s.namespace = "memanto_agent_agent-1"
    s.session_token = "jwt-token"
    s.started_at = datetime.now(timezone.utc)
    s.expires_at = datetime.now(timezone.utc) + timedelta(hours=6)
    s.status = "active"
    s.is_active.return_value = True
    return s


class TestDirectClientSessionId:
    """Verify remember / batch_remember pass the real session_id."""

    def test_remember_uses_real_session_id(self, tmp_path):
        from memanto.cli.client.direct_client import DirectClient

        client = DirectClient.__new__(DirectClient)
        client.api_key = "test-key"
        client.agent_id = "agent-1"
        client.session_token = "jwt-token"
        client._cached_session = _make_session("sess_real_42")
        for attr in [
            "_moorcheh", "_write_service", "_read_service",
            "_agent_service", "_session_service",
            "_daily_analysis_service", "_export_service",
        ]:
            setattr(client, attr, None)
        client._validate_memory_input = MagicMock()

        mock_ws = MagicMock()
        mock_ws.store_memory.return_value = {
            "id": "mem-1", "namespace": "ns", "status": "queued"
        }
        client._get_write_service = MagicMock(return_value=mock_ws)

        mock_ss = MagicMock()
        client._get_session_service = MagicMock(return_value=mock_ss)

        with patch(
            "memanto.cli.client.direct_client.is_successful_write_result",
            return_value=True,
        ):
            client.remember(
                agent_id="agent-1", memory_type="fact", title="t", content="c"
            )

        mock_ss.try_log_memory_to_session_summary.assert_called_once()
        kw = mock_ss.try_log_memory_to_session_summary.call_args[1]
        assert kw["session_id"] == "sess_real_42", (
            f"Expected 'sess_real_42', got {kw['session_id']!r}"
        )

    def test_batch_remember_uses_real_session_id(self, tmp_path):
        from memanto.cli.client.direct_client import DirectClient

        client = DirectClient.__new__(DirectClient)
        client.api_key = "test-key"
        client.agent_id = "agent-1"
        client.session_token = "jwt-token"
        client._cached_session = _make_session("sess_real_99")
        for attr in [
            "_moorcheh", "_write_service", "_read_service",
            "_agent_service", "_session_service",
            "_daily_analysis_service", "_export_service",
        ]:
            setattr(client, attr, None)
        client._validate_memory_input = MagicMock()

        mock_ws = MagicMock()
        mock_ws.batch_store_memories.return_value = {
            "total_submitted": 1, "successful": 1, "failed": 0,
            "namespace": "ns",
            "results": [{"id": "mem-1", "status": "queued", "action": "store"}],
        }
        client._get_write_service = MagicMock(return_value=mock_ws)

        mock_ss = MagicMock()
        client._get_session_service = MagicMock(return_value=mock_ss)

        with patch(
            "memanto.cli.client.direct_client.is_successful_write_result",
            return_value=True,
        ):
            client.batch_remember(
                agent_id="agent-1",
                memories=[{"content": "hello", "type": "fact"}],
            )

        mock_ss.try_log_memory_to_session_summary.assert_called_once()
        kw = mock_ss.try_log_memory_to_session_summary.call_args[1]
        assert kw["session_id"] == "sess_real_99", (
            f"Expected 'sess_real_99', got {kw['session_id']!r}"
        )


class TestSDKClientSessionId:
    """Same checks for the moorcheh-sdk-backed client."""

    def test_remember_uses_real_session_id(self, tmp_path):
        from memanto.cli.client.sdk_client import SDKClient

        client = SDKClient.__new__(SDKClient)
        client.api_key = "test-key"
        client.agent_id = "agent-1"
        client.session_token = "jwt-token"
        client._cached_session = _make_session("sess_sdk_77")
        for attr in [
            "_sdk_client", "_write_service", "_read_service",
            "_agent_service", "_session_service",
            "_daily_analysis_service", "_export_service",
        ]:
            setattr(client, attr, None)
        client._validate_memory_input = MagicMock()

        mock_ws = MagicMock()
        mock_ws.store_memory.return_value = {
            "id": "mem-1", "namespace": "ns", "status": "queued"
        }
        client._get_write_service = MagicMock(return_value=mock_ws)

        mock_ss = MagicMock()
        client._get_session_service = MagicMock(return_value=mock_ss)

        with patch(
            "memanto.cli.client.sdk_client.is_successful_write_result",
            return_value=True,
        ):
            client.remember(
                agent_id="agent-1", memory_type="fact", title="t", content="c"
            )

        mock_ss.try_log_memory_to_session_summary.assert_called_once()
        kw = mock_ss.try_log_memory_to_session_summary.call_args[1]
        assert kw["session_id"] == "sess_sdk_77"

    def test_batch_remember_uses_real_session_id(self, tmp_path):
        from memanto.cli.client.sdk_client import SDKClient

        client = SDKClient.__new__(SDKClient)
        client.api_key = "test-key"
        client.agent_id = "agent-1"
        client.session_token = "jwt-token"
        client._cached_session = _make_session("sess_sdk_88")
        for attr in [
            "_sdk_client", "_write_service", "_read_service",
            "_agent_service", "_session_service",
            "_daily_analysis_service", "_export_service",
        ]:
            setattr(client, attr, None)
        client._validate_memory_input = MagicMock()

        mock_ws = MagicMock()
        mock_ws.batch_store_memories.return_value = {
            "total_submitted": 1, "successful": 1, "failed": 0,
            "namespace": "ns",
            "results": [{"id": "mem-1", "status": "queued", "action": "store"}],
        }
        client._get_write_service = MagicMock(return_value=mock_ws)

        mock_ss = MagicMock()
        client._get_session_service = MagicMock(return_value=mock_ss)

        with patch(
            "memanto.cli.client.sdk_client.is_successful_write_result",
            return_value=True,
        ):
            client.batch_remember(
                agent_id="agent-1",
                memories=[{"content": "hello", "type": "fact"}],
            )

        mock_ss.try_log_memory_to_session_summary.assert_called_once()
        kw = mock_ss.try_log_memory_to_session_summary.call_args[1]
        assert kw["session_id"] == "sess_sdk_88"
