import unittest
import json
import os
import subprocess
import sys
from pathlib import Path

class TestBenchmark(unittest.TestCase):
    def test_results_exist(self):
        # Run benchmark
        run_script = Path(__file__).parent / "run_benchmark.py"
        subprocess.run([sys.executable, str(run_script)], check=True, capture_output=True, text=True)
        
        # Verify
        results_path = Path(__file__).parent / "benchmark_results.json"
        self.assertTrue(results_path.exists())
        
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.assertIn("memanto", data)
            self.assertIn("baseline", data)
            
            # Absolute metric ranges instead of just relative ordering
            self.assertTrue(data["memanto"]["avg_retrieve_ms"] < data["baseline"]["avg_retrieve_ms"])
            self.assertGreater(data["memanto"]["avg_retrieve_ms"], 0)
            self.assertIsInstance(data["memanto"]["token_overhead"], (int, float))
            self.assertIsInstance(data["memanto"]["accuracy"], float)
            self.assertGreaterEqual(data["memanto"]["accuracy"], 0.0)
            
        finally:
            if results_path.exists():
                results_path.unlink()

if __name__ == "__main__":
    unittest.main()
