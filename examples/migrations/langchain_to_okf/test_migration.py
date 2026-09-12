"""
Unit and Integration Test for LangChain -> OKF Migration Adapter.
"""

import os
import json
import shutil
import tempfile
import yaml
from migrate import parse_langchain_history, export_to_okf_bundle

def test_migration_pipeline():
    sample_langchain_data = [
        {
            "type": "system",
            "content": "You are a code architecture review agent configured for microservices.",
            "additional_kwargs": {"timestamp": "2026-08-15T10:00:00Z"}
        },
        {
            "type": "human",
            "content": "We decided to migrate authentication from session cookies to JWT tokens.",
            "additional_kwargs": {"timestamp": "2026-08-15T10:05:00Z"}
        },
        {
            "type": "ai",
            "content": "I always prefer using RS256 asymmetric signing over HS256 for cross-service verification.",
            "additional_kwargs": {"timestamp": "2026-08-15T10:06:00Z"}
        }
    ]

    temp_dir = tempfile.mkdtemp()
    try:
        memories = parse_langchain_history(sample_langchain_data)
        assert len(memories) == 3, f"Expected 3 memories, got {len(memories)}"
        
        assert memories[0]["type"] == "context"
        assert memories["type"] == "decision"
        assert memories["type"] == "preference"

        export_to_okf_bundle(memories, temp_dir)

        manifest_path = os.path.join(temp_dir, "manifest.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path) as f:
            manifest = json.load(f)
            assert manifest["okf_version"] == "0.2.0"
            assert manifest["total_memories"] == 3

        memories_dir = os.path.join(temp_dir, "memories")
        files = os.listdir(memories_dir)
        assert len(files) == 3

        for file in files:
            with open(os.path.join(memories_dir, file), "r", encoding="utf-8") as f:
                content = f.read()
                parts = content.split("---")
                assert len(parts) >= 3, "Missing valid YAML frontmatter"
                metadata = yaml.safe_load(parts)
                assert "id" in metadata
                assert "type" in metadata
                assert metadata["source"] == "langchain"

        print("[✓] All migration assertions passed successfully!")
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    test_migration_pipeline()