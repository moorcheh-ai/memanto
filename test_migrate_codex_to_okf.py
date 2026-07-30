import unittest
import json
import os
from migrate_codex_to_okf import migrate_codex_to_okf

class TestMigrateCodexToOKF(unittest.TestCase):
    def test_migration(self):
        # Create a test Codex JSONL file
        with open('test_codex.jsonl', 'w') as f:
            f.write(json.dumps({'type': 'user', 'text': 'Hello', 'source': 'path/to/source'}) + '\n')
            f.write(json.dumps({'type': 'assistant', 'text': 'Hi', 'source': 'path/to/source'}) + '\n')
        # Run the migration
        migrate_codex_to_okf('test_codex.jsonl', 'test_okf.okf')
        # Check the resulting OKF file
        with open('test_okf.okf', 'r') as f:
            okf_data = json.load(f)
            self.assertEqual(len(okf_data), 2)
            self.assertEqual(okf_data[0]['type'], 'user')
            self.assertEqual(okf_data[0]['text'], 'Hello')
            self.assertEqual(okf_data[1]['type'], 'assistant')
            self.assertEqual(okf_data[1]['text'], 'Hi')
        # Clean up
        os.remove('test_codex.jsonl')
        os.remove('test_okf.okf')

if __name__ == '__main__':
    unittest.main()