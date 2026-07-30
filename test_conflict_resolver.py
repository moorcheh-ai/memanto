# -*- coding: utf-8 -*-
import unittest
import json
import os
from conflict_resolver import list_conflicts, resolve_conflict

class TestConflictResolver(unittest.TestCase):
    def setUp(self):
        self.report_path = 'test_report.json'
        self.memories_path = 'memories'
        os.mkdir(self.memories_path)
        with open(self.report_path, 'w') as f:
            json.dump([
                {'resolved': True, 'old': 'mem-old-0', 'new': 'mem-new-0'},
                {'resolved': False, 'old': 'mem-old-1', 'new': 'mem-new-1'},
                {'resolved': False, 'old': 'mem-old-2', 'new': 'mem-new-2'}
            ], f)
        with open(os.path.join(self.memories_path, 'mem-old-0'), 'w') as f:
            f.write('mem-old-0 content')
        with open(os.path.join(self.memories_path, 'mem-new-0'), 'w') as f:
            f.write('mem-new-0 content')
        with open(os.path.join(self.memories_path, 'mem-old-1'), 'w') as f:
            f.write('mem-old-1 content')
        with open(os.path.join(self.memories_path, 'mem-new-1'), 'w') as f:
            f.write('mem-new-1 content')
        with open(os.path.join(self.memories_path, 'mem-old-2'), 'w') as f:
            f.write('mem-old-2 content')
        with open(os.path.join(self.memories_path, 'mem-new-2'), 'w') as f:
            f.write('mem-new-2 content')
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.memories_path)
        os.remove(self.report_path)
    
    def test_list_conflicts(self):
        conflicts = list_conflicts(self.report_path)
        self.assertEqual(len(conflicts), 2)
    
    def test_resolve_conflict(self):
        result = resolve_conflict(self.report_path, 0)
        self.assertEqual(result['deleted_old'], 'mem-old-1')
        self.assertEqual(result['deleted_new'], 'mem-new-1')
        self.assertEqual(result['status'], 'resolved')
        with open(self.report_path, 'r') as f:
            report = json.load(f)
        self.assertTrue(report[1]['resolved'])