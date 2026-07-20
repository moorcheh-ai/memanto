import unittest
from unittest.mock import patch, MagicMock
from memanto.cli.connect.engine import install_agent, remove_agent

class TestConnectEngine(unittest.TestCase):
    @patch("memanto.cli.connect.engine._install_instructions")
    @patch("memanto.cli.connect.engine._install_skill")
    @patch("memanto.cli.connect.engine._install_hooks")
    @patch("memanto.cli.connect.engine._install_permissions")
    def test_install_agent(
        self, mock_install_permissions, mock_install_hooks, mock_install_skill, mock_install_instructions
    ):
        agent_name = "test_agent"
        project_dir = "/test/project"
        is_global = False

        mock_install_instructions.return_value = "Installed instructions"
        mock_install_skill.return_value = "Installed skill"
        mock_install_hooks.return_value = "Installed hooks"
        mock_install_permissions.return_value = "Installed permissions"

        result = install_agent(agent_name, project_dir, is_global)

        self.assertEqual(result["agent"], agent_name)
        self.assertEqual(result["steps"], ["Installed instructions", "Installed skill", "Installed hooks", "Installed permissions"])
        self.assertEqual(result["errors"], [])

    @patch("memanto.cli.connect.engine._remove_instructions")
    @patch("memanto.cli.connect.engine._remove_skill")
    @patch("memanto.cli.connect.engine._remove_hooks")
    @patch("memanto.cli.connect.engine._remove_permissions")
    def test_remove_agent(
        self, mock_remove_permissions, mock_remove_hooks, mock_remove_skill, mock_remove_instructions
    ):
        agent_name = "test_agent"
        project_dir = "/test/project"
        is_global = False

        mock_remove_instructions.return_value = "Removed instructions"
        mock_remove_skill.return_value = "Removed skill"
        mock_remove_hooks.return_value = "Removed hooks"
        mock_remove_permissions.return_value = "Removed permissions"

        result = remove_agent(agent_name, project_dir, is_global)

        self.assertEqual(result["agent"], agent_name)
        self.assertEqual(result["steps"], ["Removed instructions", "Removed skill", "Removed hooks", "Removed permissions"])
        self.assertEqual(result["errors"], [])