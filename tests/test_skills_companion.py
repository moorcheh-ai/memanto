from unittest.mock import MagicMock, patch
import pytest
import argparse
import sys
from pathlib import Path

# Add examples directory to sys.path to import memanto_skills directly
SKILLS_DIR = Path(__file__).parent.parent / "examples" / "claudecode-skills-memanto"
sys.path.insert(0, str(SKILLS_DIR))

from memanto_skills import handle_start, handle_end


def test_memanto_skills_end():
    """Test that the end command distills and saves the decision memory correctly."""
    with patch("memanto_skills.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        mock_client.remember.return_value = {"memory_id": "test-mem-123"}
        
        args_end = argparse.Namespace(
            command="end",
            task="Test architectural choice",
            summary="Use asyncio for all database calls.",
            confidence=0.9,
            tags="db,async,preference",
            agent_id="test-agent"
        )
        
        handle_end(args_end)
        
        # Verify remember was called correctly with distilled memory_type="preference"
        mock_client.remember.assert_called_once_with(
            agent_id="test-agent",
            memory_type="preference",
            title="Decision: Test architectural choice",
            content="Use asyncio for all database calls.",
            confidence=0.9,
            tags=["db", "async", "preference"],
            source="claudecode-skills",
            provenance="skills_companion",
        )


def test_memanto_skills_start(tmp_path):
    """Test that the start command queries Memanto and injects context into the workspace."""
    out_file = tmp_path / "skills_memory.md"
    
    with patch("memanto_skills.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock recall to return a relevant memory
        mock_client.recall.return_value = {
            "memories": [
                {
                    "type": "decision",
                    "title": "Decision: Test architectural choice",
                    "content": "Use asyncio for all database calls.",
                    "confidence": 0.9,
                    "tags": ["db", "async"]
                }
            ]
        }
        
        args_start = argparse.Namespace(
            command="start",
            task="Implement user model",
            file="user.py",
            agent_id="test-agent",
            out_file=str(out_file)
        )
        
        handle_start(args_start)
        
        # Verify recall was called with the correct built query
        mock_client.recall.assert_called_once_with(
            agent_id="test-agent",
            query="Implement user model in file user.py",
            limit=5,
            min_similarity=0.3
        )
        
        # Verify the context file was generated and has the expected content
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Use asyncio for all database calls." in content
        assert "Test architectural choice" in content
        assert "Implement user model" in content
