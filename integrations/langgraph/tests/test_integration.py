"""
Unit tests for the LangGraph + Memanto integration.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestRememberInput:
    def test_valid_memory_types(self):
        from langgraph_memanto.tools import RememberInput
        valid_types = [
            'fact', 'preference', 'goal', 'decision', 'artifact',
            'learning', 'event', 'instruction', 'relationship',
            'context', 'observation', 'commitment', 'error',
        ]
        for mt in valid_types:
            inp = RememberInput(
                memory_type=mt, title='Test', content='Test content', confidence=0.8,
            )
            assert inp.memory_type == mt

    def test_confidence_bounds(self):
        from langgraph_memanto.tools import RememberInput
        with pytest.raises(Exception):
            RememberInput(memory_type='fact', title='Test', content='Test', confidence=1.5)
        with pytest.raises(Exception):
            RememberInput(memory_type='fact', title='Test', content='Test', confidence=-0.5)

    def test_tags_default(self):
        from langgraph_memanto.tools import RememberInput
        inp = RememberInput(memory_type='fact', title='Test', content='Test content', confidence=0.8)
        assert inp.tags == ''


class TestRecallInput:
    def test_defaults(self):
        from langgraph_memanto.tools import RecallInput
        inp = RecallInput(query='test')
        assert inp.limit == 5
        assert inp.memory_types == ''


class TestAnswerInput:
    def test_question_required(self):
        from langgraph_memanto.tools import AnswerInput
        with pytest.raises(Exception):
            AnswerInput()


class TestCreateMemantoTools:
    @patch('langgraph_memanto.tools.SdkClient')
    def test_returns_three_tools(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        mock_client.remember.return_value = {
            'memory_id': 'mem-123', 'agent_id': 'test-agent',
            'namespace': 'memanto_agent_test-agent', 'status': 'queued', 'confidence': 0.8,
        }
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        assert 'remember' in tools
        assert 'recall' in tools
        assert 'answer' in tools

    @patch('langgraph_memanto.tools.SdkClient')
    def test_remember_invocation(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        mock_client.remember.return_value = {
            'memory_id': 'mem-123', 'agent_id': 'test-agent',
            'namespace': 'memanto_agent_test-agent', 'status': 'queued', 'confidence': 0.9,
        }
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        result = tools['remember'].invoke({
            'memory_type': 'fact', 'title': 'Test fact',
            'content': 'This is a test fact', 'confidence': 0.9, 'tags': 'test,demo',
        })
        mock_client.remember.assert_called_once()
        call_kwargs = mock_client.remember.call_args[1]
        assert call_kwargs['memory_type'] == 'fact'
        assert call_kwargs['tags'] == ['test', 'demo']
        assert 'mem-123' in result

    @patch('langgraph_memanto.tools.SdkClient')
    def test_recall_invocation(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        mock_client.recall.return_value = {
            'agent_id': 'test-agent', 'query': 'test query',
            'memories': [{'title': 'Test', 'content': 'test', 'type': 'fact', 'confidence': 0.9, 'tags': []}],
            'count': 1,
        }
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        result = tools['recall'].invoke({'query': 'test query', 'limit': 5})
        mock_client.recall.assert_called_once()
        assert 'Found 1 memories' in result

    @patch('langgraph_memanto.tools.SdkClient')
    def test_recall_empty(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        mock_client.recall.return_value = {
            'agent_id': 'test-agent', 'query': 'nonexistent', 'memories': [], 'count': 0,
        }
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        result = tools['recall'].invoke({'query': 'nonexistent', 'limit': 5})
        assert 'No memories found' in result

    @patch('langgraph_memanto.tools.SdkClient')
    def test_answer_invocation(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        mock_client.answer.return_value = {
            'agent_id': 'test-agent', 'question': 'What is the rate limit?',
            'answer': 'The rate limit is 100 req/min',
            'sources': [{'id': 'mem-1'}], 'namespace': 'memanto_agent_test-agent',
        }
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        result = tools['answer'].invoke({'question': 'What is the rate limit?'})
        mock_client.answer.assert_called_once()
        assert '100 req/min' in result

    @patch('langgraph_memanto.tools.SdkClient')
    def test_tool_names(self, MockSdkClient):
        from langgraph_memanto.tools import create_memanto_tools
        mock_client = MockSdkClient.return_value
        tools = create_memanto_tools(mock_client, agent_id='test-agent')
        assert tools['remember'].name == 'memanto_remember'
        assert tools['recall'].name == 'memanto_recall'
        assert tools['answer'].name == 'memanto_answer'


class TestAgentState:
    def test_default_values(self):
        from langgraph_memanto.graph import AgentState
        state = AgentState()
        assert state.query == ''
        assert state.classification == 'unknown'
        assert state.memories_found == 0
        assert state.memories_stored == 0

    def test_custom_values(self):
        from langgraph_memanto.graph import AgentState
        state = AgentState(query='test query', classification='recall', memories_found=3)
        assert state.query == 'test query'
        assert state.classification == 'recall'
        assert state.memories_found == 3


class TestQueryClassification:
    def test_valid_actions(self):
        from langgraph_memanto.graph import QueryClassification
        for action in ['recall', 'remember', 'answer']:
            qc = QueryClassification(action=action)
            assert qc.action == action

    def test_invalid_action(self):
        from langgraph_memanto.graph import QueryClassification
        with pytest.raises(Exception):
            QueryClassification(action='invalid')


class TestSetup:
    @patch('langgraph_memanto.setup.SdkClient')
    def test_setup_creates_agent(self, MockSdkClient):
        mock_client = MockSdkClient.return_value
        mock_client.activate_agent.return_value = {
            'session_token': 'tok-123', 'session_id': 'sess-1',
            'agent_id': 'test-agent', 'namespace': 'memanto_agent_test-agent',
            'expires_at': '2026-05-23T00:00:00',
        }
        from langgraph_memanto.setup import MemantoSetup
        memanto_setup = MemantoSetup(api_key='test-key')
        result = memanto_setup.setup(agent_id='test-agent')
        mock_client.create_agent.assert_called_once()
        mock_client.activate_agent.assert_called_once()

    @patch('langgraph_memanto.setup.SdkClient')
    def test_teardown(self, MockSdkClient):
        mock_client = MockSdkClient.return_value
        mock_client.deactivate_agent.return_value = {'status': 'ended', 'agent_id': 'test-agent'}
        from langgraph_memanto.setup import MemantoSetup
        memanto_setup = MemantoSetup(api_key='test-key')
        memanto_setup.teardown(agent_id='test-agent')
        mock_client.deactivate_agent.assert_called_once()
