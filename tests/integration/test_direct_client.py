import os
import tempfile
import unittest
from pathlib import Path

from memanto.config import get_data_dir
from memanto.clients.direct_client import DirectClient

class TestDirectClient(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.agent_id = "test_agent"
        self.okf_data = {"key": "value"}

    def tearDown(self):
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    def test_sync_okf_to_project(self):
        """Test that OKF data is synced from the backend-specific cache."""
        with unittest.mock.patch("memanto.config.get_data_dir", return_value=self.test_dir):
            client = DirectClient(self.agent_id)
            # Create a test cache file
            cache_dir = os.path.join(self.test_dir, "exports")
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, f"{self.agent_id}_okf")
            with open(cache_path, "w") as f:
                f.write(str(self.okf_data))
            # Test sync
            result = client.sync_okf_to_project()
            self.assertTrue(result)

    def test_sync_okf_to_project_no_cache(self):
        """Test that sync fails when no cache exists."""
        with unittest.mock.patch("memanto.config.get_data_dir", return_value=self.test_dir):
            client = DirectClient(self.agent_id)
            result = client.sync_okf_to_project()
            self.assertFalse(result)