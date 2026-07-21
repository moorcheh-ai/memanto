import unittest
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService

class TestMemoryParsingService(unittest.TestCase):
    def setUp(self):
        self.service = MemoryParsingService()

    def test_negated_preference_classification(self):
        test_cases = [
            ("I don't like Python", "preference"),
            ("I do not like dark mode", "preference"),
            ("I no longer like Vim", "preference"),
            ("I never liked that", "preference"),
            ("I can't stand this", "preference"),
            ("I prefer not to use this", "preference"),
            ("Don't deploy unpinned dependencies in production", "instruction")
        ]

        for content, expected_type in test_cases:
            memory = MemoryRecord(
                content=content,
                type=None,
                title="test",
                actor_id="user",
                source="test",
                agent_id="agent"
            )
            self.service.parse_memory(memory)
            self.assertEqual(memory.type, expected_type)

if __name__ == '__main__':
    unittest.main()