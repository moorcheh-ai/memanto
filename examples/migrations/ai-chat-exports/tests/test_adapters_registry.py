import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import adapters  # noqa: F401
from core.adapters import ADAPTERS


class TestAdapterRegistry:
    def test_chatgpt_registered(self):
        assert "chatgpt" in ADAPTERS

    def test_claude_registered(self):
        assert "claude" in ADAPTERS

    def test_gemini_registered(self):
        assert "gemini" in ADAPTERS

    def test_registry_has_three_adapters(self):
        assert len(ADAPTERS) == 3

    def test_adapter_has_required_methods(self):
        for name, cls in ADAPTERS.items():
            assert hasattr(cls, "name"), f"{name} missing 'name'"
            assert hasattr(cls, "load"), f"{name} missing 'load'"
            assert hasattr(cls, "extract"), f"{name} missing 'extract'"
            assert hasattr(cls, "get_source_stats"), (
                f"{name} missing 'get_source_stats'"
            )
