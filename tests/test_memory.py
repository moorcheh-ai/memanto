import unittest
from datetime import datetime
from memanto.memory import MemoryRecord

class TestMemoryRecord(unittest.TestCase):
    def test_update_preserves_provenance(self):
        """
        Test that updating a memory preserves the original provenance unless explicitly changed.
        """
        original_provenance = "validated"
        memory = MemoryRecord(
            content="Original content",
            metadata={"key": "value"},
            provenance=original_provenance
        )

        # Update with new content and metadata, but no provenance change
        memory.update(
            content="Updated content",
            metadata={"new_key": "new_value"}
        )

        # Verify provenance is preserved
        self.assertEqual(memory.provenance, original_provenance)
        self.assertEqual(memory.content, "Updated content")
        self.assertIn("key", memory.metadata)
        self.assertIn("new_key", memory.metadata)

    def test_update_changes_provenance(self):
        """
        Test that updating a memory with a new provenance changes the provenance.
        """
        original_provenance = "validated"
        memory = MemoryRecord(
            content="Original content",
            metadata={"key": "value"},
            provenance=original_provenance
        )

        # Update with new provenance
        new_provenance = "corrected"
        memory.update(provenance=new_provenance)

        # Verify provenance is updated
        self.assertEqual(memory.provenance, new_provenance)