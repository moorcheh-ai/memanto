"""Test that remember/batch_remember use session.session_id, not hardcoded 'unknown'.

Regression tests for the bug where session_id was hardcoded to "unknown"
in SdkClient.remember(), SdkClient.batch_remember(), DirectClient.remember(),
and DirectClient.batch_remember(), causing session summary files to be named
with 'unknown' instead of the actual session ID.

Refs #770
"""

from unittest.mock import MagicMock, patch
import pytest


def _make_session(session_id="sess_abc123"):
    session = MagicMock()
    session.session_id = session_id
    session.agent_id = "agent1"
    session.namespace = "memanto_agent_agent1"
    session.is_active.return_value = True
    return session


def _make_write_service():
    svc = MagicMock()
    result = {"id": "mem_1", "status": "queued", "namespace": "memanto_agent_agent1", "type": "fact"}
    svc.store_memory.return_value = result
    svc.batch_store_memories.return_value = {
        "total_submitted": 1, "successful": 1, "failed": 0, "results": [result],
    }
    return svc


def _make_session_service():
    svc = MagicMock()
    svc.try_log_memory_to_session_summary.return_value = True
    return svc


class TestSdkClientRememberUsesSessionId:
    @patch("memanto.cli.client.sdk_client.SdkClient._get_session_service")
    @patch("memanto.cli.client.sdk_client.SdkClient._get_write_service")
    @patch("memanto.cli.client.sdk_client.SdkClient._get_validated_session_for_agent")
    @patch("memanto.cli.client.sdk_client.is_successful_write_result", return_value=True)
    def test_remember_uses_session_id(self, mock_ok, mock_sess, mock_write, mock_sess_svc):
        from memanto.cli.client.sdk_client import SdkClient
        session = _make_session(session_id="sess_real_42")
        mock_sess.return_value = session
        mock_write.return_value = _make_write_service()
        mock_sess_svc.return_value = _make_session_service()
        client = SdkClient.__new__(SdkClient)
        client.session_token = "tok"
        client.agent_id = "agent1"
        client._cached_session = session
        client.remember(agent_id="agent1", memory_type="fact", title="T", content="C")
        kw = mock_sess_svc.return_value.try_log_memory_to_session_summary.call_args.kwargs
        assert kw.get("session_id") == "sess_real_42", f"got {kw.get('session_id')!r}"


class TestSdkClientBatchRememberUsesSessionId:
    @patch("memanto.cli.client.sdk_client.SdkClient._get_session_service")
    @patch("memanto.cli.client.sdk_client.SdkClient._get_write_service")
    @patch("memanto.cli.client.sdk_client.SdkClient._get_validated_session_for_agent")
    @patch("memanto.cli.client.sdk_client.is_successful_write_result", return_value=True)
    def test_batch_uses_session_id(self, mock_ok, mock_sess, mock_write, mock_sess_svc):
        from memanto.cli.client.sdk_client import SdkClient
        session = _make_session(session_id="sess_batch_99")
        mock_sess.return_value = session
        mock_write.return_value = _make_write_service()
        mock_sess_svc.return_value = _make_session_service()
        client = SdkClient.__new__(SdkClient)
        client.session_token = "tok"
        client.agent_id = "agent1"
        client._cached_session = session
        client.batch_remember(agent_id="agent1", memories=[{"content": "C", "type": "fact"}])
        kw = mock_sess_svc.return_value.try_log_memory_to_session_summary.call_args.kwargs
        assert kw.get("session_id") == "sess_batch_99", f"got {kw.get('session_id')!r}"


class TestDirectClientRememberUsesSessionId:
    @patch("memanto.cli.client.direct_client.DirectClient._get_session_service")
    @patch("memanto.cli.client.direct_client.DirectClient._get_write_service")
    @patch("memanto.cli.client.direct_client.DirectClient._get_validated_session_for_agent")
    @patch("memanto.cli.client.direct_client.is_successful_write_result", return_value=True)
    def test_remember_uses_session_id(self, mock_ok, mock_sess, mock_write, mock_sess_svc):
        from memanto.cli.client.direct_client import DirectClient
        session = _make_session(session_id="sess_direct_77")
        mock_sess.return_value = session
        mock_write.return_value = _make_write_service()
        mock_sess_svc.return_value = _make_session_service()
        client = DirectClient.__new__(DirectClient)
        client.session_token = "tok"
        client.agent_id = "agent1"
        client._cached_session = session
        client.remember(agent_id="agent1", memory_type="fact", title="T", content="C")
        kw = mock_sess_svc.return_value.try_log_memory_to_session_summary.call_args.kwargs
        assert kw.get("session_id") == "sess_direct_77", f"got {kw.get('session_id')!r}"


class TestDirectClientBatchRememberUsesSessionId:
    @patch("memanto.cli.client.direct_client.DirectClient._get_session_service")
    @patch("memanto.cli.client.direct_client.DirectClient._get_write_service")
    @patch("memanto.cli.client.direct_client.DirectClient._get_validated_session_for_agent")
    @patch("memanto.cli.client.direct_client.is_successful_write_result", return_value=True)
    def test_batch_uses_session_id(self, mock_ok, mock_sess, mock_write, mock_sess_svc):
        from memanto.cli.client.direct_client import DirectClient
        session = _make_session(session_id="sess_direct_batch_55")
        mock_sess.return_value = session
        mock_write.return_value = _make_write_service()
        mock_sess_svc.return_value = _make_session_service()
        client = DirectClient.__new__(DirectClient)
        client.session_token = "tok"
        client.agent_id = "agent1"
        client._cached_session = session
        client.batch_remember(agent_id="agent1", memories=[{"content": "C", "type": "fact"}])
        kw = mock_sess_svc.return_value.try_log_memory_to_session_summary.call_args.kwargs
        assert kw.get("session_id") == "sess_direct_batch_55", f"got {kw.get('session_id')!r}"
