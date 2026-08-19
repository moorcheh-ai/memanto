
import pytest
from pathlib import Path
from memanto.cli.migrate.okf_loader import load_okf_bundle
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.runner import run_migration
from unittest.mock import MagicMock

def test_okf_agent_id_preservation(tmp_path):
    """Verify that agent_id is preserved through loader and mapper."""
    okf_content = """---
type: fact
title: Multi-Agent Test
agent_id: agent_alpha
tags: [test]
---
This is a memory for Alpha.
"""
    test_file = tmp_path / "test_memory.md"
    test_file.write_text(okf_content)
    
    # 1. Test Loader
    bundle = load_okf_bundle(test_file)
    entry = bundle['memories'][0]
    assert entry.get('agent_id') == 'agent_alpha'
    
    # 2. Test Mapper
    mapped = map_okf(bundle)
    payload = mapped[0]
    assert payload.get('agent_id') == 'agent_alpha'

def test_run_migration_multi_agent_grouping():
    """Verify that run_migration groups batches by agent_id correctly."""
    # Mock data with different agents
    rows = [
        {"title": "M1", "content": "C1", "agent_id": "agent_1"},
        {"title": "M2", "content": "C2", "agent_id": "agent_1"},
        {"title": "M3", "content": "C3", "agent_id": "agent_2"},
    ]
    
    mock_client = MagicMock()
    mock_client.batch_remember.return_value = {"results": [], "successful": 1, "failed": 0}
    
    # We need to mock map_export to return our custom rows
    import memanto.cli.migrate.runner as runner
    original_map_export = runner.map_export
    runner.map_export = MagicMock(return_value=rows)
    
    try:
        summary, _ = run_migration(
            provider="okf",
            export={},
            client=mock_client,
            agent_id="default_agent", # This should be overridden by row['agent_id']
            dry_run=False
        )
        
        # Verify batch_remember was called twice (once per agent)
        assert mock_client.batch_remember.call_count == 2
        
        # Verify first call was for agent_1
        args, kwargs = mock_client.batch_remember.call_args_list[0]
        assert kwargs['agent_id'] == 'agent_1'
        assert len(kwargs['memories']) == 2
        
        # Verify second call was for agent_2
        args, kwargs = mock_client.batch_remember.call_args_list[1]
        assert kwargs['agent_id'] == 'agent_2'
        assert len(kwargs['memories']) == 1
        
    finally:
        runner.map_export = original_map_export
