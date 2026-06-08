import unittest
import json
import os

class TestBenchmark(unittest.TestCase):
    def test_results_exist(self):
        # Run benchmark
        os.system("python3 run_benchmark.py")
        
        # Verify
        self.assertTrue(os.path.exists("benchmark_results.json"))
        with open("benchmark_results.json", "r") as f:
            data = json.load(f)
            
        self.assertIn("memanto", data)
        self.assertIn("baseline", data)
        self.assertTrue(data["memanto"]["avg_retrieve_ms"] < data["baseline"]["avg_retrieve_ms"])

if __name__ == "__main__":
    unittest.main()
