import unittest
from n8n_executions_to_okf import N8nExecutionToOKF

class TestN8nExecutionToOKF(unittest.TestCase):
    def test_convert_to_okf(self):
        n8n_executions = [
            {'id': '1', 'data': {'score': '10', 'email': 'example@example.com'}},
            {'id': '2', 'data': {'score': '20', 'email': 'example2@example.com'}},
            {'id': '3', 'data': {'score': '30', 'email': 'example3@example.com'}}
        ]
        converter = N8nExecutionToOKF(n8n_executions)
        okf_memories = converter.convert_to_okf()
        self.assertEqual(len(okf_memories), 3)

    def test_add_field_level_mapping(self):
        n8n_executions = [
            {'id': '1', 'data': {'score': '10', 'email': 'example@example.com'}},
            {'id': '2', 'data': {'score': '20', 'email': 'example2@example.com'}},
            {'id': '3', 'data': {'score': '30', 'email': 'example3@example.com'}}
        ]
        converter = N8nExecutionToOKF(n8n_executions)
        okf_memories = converter.convert_to_okf()
        okf_memories = converter.add_field_level_mapping(okf_memories)
        self.assertIn('score', okf_memories[0]['data'])

    def test_add_privacy_controls(self):
        n8n_executions = [
            {'id': '1', 'data': {'score': '10', 'email': 'example@example.com'}},
            {'id': '2', 'data': {'score': '20', 'email': 'example2@example.com'}},
            {'id': '3', 'data': {'score': '30', 'email': 'example3@example.com'}}
        ]
        converter = N8nExecutionToOKF(n8n_executions)
        okf_memories = converter.convert_to_okf()
        okf_memories = converter.add_field_level_mapping(okf_memories)
        okf_memories = converter.add_privacy_controls(okf_memories)
        self.assertNotIn('email', okf_memories[0]['data'])

if __name__ == '__main__':
    unittest.main()