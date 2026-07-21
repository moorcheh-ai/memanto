import unittest
from memanto.storage import MemoryStorage
from memanto.memory import MemoryRecord

class TestMemoryStorage(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryStorage()
        self.memory_id = "test_memory"
        self.original_provenance = "validated"
        self.memory = MemoryRecord(
            content="Original content",
            metadata={"key": "value"},
            provenance=self.original_provenance
        )
        self.storage.memories[self.memory_id] = self.memory

    def test_update_memory_preserves_provenance(self):
        """
        Test that updating a memory through the storage preserves the original provenance unless explicitly changed.
        """
        updated_memory = self.storage.update_memory(
            memory_id=self.memory_id,
            content="Updated content",
            metadata={"new_key": "new_value"}
        )

        # Verify provenance is preserved
        self.assertEqual(updated_memory.provenance, self.original_provenance)
        self.assertEqual(updated_memory.content, "Updated content")
        self.assertIn("key", updated_memory.metadata)
        self.assertIn("new_key", updated_memory.metadata)

    def test_update_memory_changes_provenance(self):
        """
        Test that updating a memory through the storage with a new provenance changes the provenance.
        """
        new_provenance = "corrected"
        updated_memory = self.storage.update_memory(
            memory_id=self.memory_id,
            provenance=new_provenance
        )

        # Verify provenance is updated
        self.assertEqual(updated_memory.provenance, new_provenance)