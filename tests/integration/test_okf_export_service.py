import os
import tempfile
import unittest
from pathlib import Path

from memanto.config import get_data_dir
from memanto.services.okf_export_service import OkfExportService

class TestOkfExportService(unittest.TestCase):
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

    def test_export_okf(self):
        """Test that OKF data is exported to the correct backend directory."""
        with unittest.mock.patch("memanto.config.get_data_dir", return_value=self.test_dir):
            service = OkfExportService()
            export_path = service.export_okf(self.agent_id, self.okf_data)
            expected_path = os.path.join(self.test_dir, "exports", f"{self.agent_id}_okf")
            self.assertEqual(export_path, expected_path)
            self.assertTrue(os.path.exists(export_path))

    def test_export_okf_custom_dir(self):
        """Test that OKF data is exported to a custom directory."""
        custom_dir = os.path.join(self.test_dir, "custom_exports")
        service = OkfExportService(custom_dir)
        export_path = service.export_okf(self.agent_id, self.okf_data)
        expected_path = os.path.join(custom_dir, f"{self.agent_id}_okf")
        self.assertEqual(export_path, expected_path)
        self.assertTrue(os.path.exists(export_path))