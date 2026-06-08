"""
Tests for the contract reconciliation memory benchmark.
Validates dataset shape, backend behavior, and report generation.
"""
import pytest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataset import generate_dataset, generate_queries, generate_memory_log
from backends import ActiveDigestBackend, AppendOnlyBackend, RecentWindowBackend


class TestDataset:
    """Test the synthetic dataset generator."""
    
    def test_dataset_size(self):
        contracts = generate_dataset(seed=42)
        assert len(contracts) == 30
        
    def test_dataset_structure(self):
        contracts = generate_dataset(seed=42)
        c = contracts[0]
        assert "contract_id" in c
        assert "counterparty" in c
        assert "signed_date" in c
        assert "value_usd" in c
        assert "active" in c
        assert "obligations" in c
        assert "payment_terms" in c
        
    def test_deterministic(self):
        d1 = generate_dataset(seed=42)
        d2 = generate_dataset(seed=42)
        assert d1 == d2
        
    def test_query_count(self):
        contracts = generate_dataset(seed=42)
        queries = generate_queries(contracts, seed=42)
        assert len(queries) == 5
        
    def test_memory_log_size(self):
        contracts = generate_dataset(seed=42)
        mem = generate_memory_log(contracts)
        assert len(mem) > 0


class TestActiveDigestBackend:
    """Test the Memanto-style active digest backend."""
    
    def test_create(self):
        backend = ActiveDigestBackend()
        backend.remember("CTR-0001", {
            "action": "create",
            "data": {"counterparty": "Acme Corp", "value_usd": 100000, "payment_terms": "net_30", "obligations": ["deliver v1"]}
        })
        all_mem = backend.get_all()
        assert len(all_mem) == 1
        assert all_mem[0]["counterparty"] == "Acme Corp"
        
    def test_terminate(self):
        backend = ActiveDigestBackend()
        backend.remember("CTR-0001", {
            "action": "create",
            "data": {"counterparty": "Acme Corp", "value_usd": 100000, "payment_terms": "net_30", "obligations": ["deliver v1"]}
        })
        backend.remember("CTR-0001", {
            "action": "terminate",
            "data": {"reason": "mutual_agreement"}
        })
        all_mem = backend.get_all()
        assert all_mem[0]["terminated"] == True
        assert all_mem[0]["active"] == False
        
    def test_update_obligations(self):
        backend = ActiveDigestBackend()
        backend.remember("CTR-0001", {
            "action": "create",
            "data": {"counterparty": "Acme Corp", "value_usd": 100000, "payment_terms": "net_30", "obligations": ["deliver v1"]}
        })
        backend.remember("CTR-0001", {
            "action": "update_obligations",
            "data": {"new_obligation": "added milestone"}
        })
        all_mem = backend.get_all()
        assert len(all_mem[0]["obligations"]) == 2
        
    def test_recall_active_with_many_obligations(self):
        backend = ActiveDigestBackend()
        # Create a contract with > 4 obligations
        obligations = [f"obligation {i}" for i in range(6)]
        backend.remember("CTR-0001", {
            "action": "create",
            "data": {"counterparty": "Acme Corp", "value_usd": 100000, "payment_terms": "net_30", "obligations": obligations}
        })
        result = backend.recall({
            "type": "filter",
            "description": "List active contracts with more than 4 obligations"
        })
        assert "CTR-0001" in result
        
    def test_recall_terminated(self):
        backend = ActiveDigestBackend()
        backend.remember("CTR-0001", {
            "action": "create",
            "data": {"counterparty": "Acme Corp", "value_usd": 100000, "payment_terms": "net_30", "obligations": ["deliver v1"]}
        })
        backend.remember("CTR-0001", {
            "action": "terminate",
            "data": {"reason": "mutual_agreement"}
        })
        result = backend.recall({
            "type": "filter",
            "description": "Terminated contract IDs"
        })
        assert "CTR-0001" in result
        
    def test_stats(self):
        backend = ActiveDigestBackend()
        stats = backend.get_stats()
        assert "total_digests" in stats
        assert "active" in stats
        assert "history_entries" in stats


class TestAppendOnlyBackend:
    """Test the passive append-only baseline."""
    
    def test_append_only(self):
        backend = AppendOnlyBackend()
        backend.remember("CTR-0001", {"action": "create", "data": {"counterparty": "Acme Corp"}})
        backend.remember("CTR-0001", {"action": "terminate", "data": {"reason": "mutual_agreement"}})
        all_mem = backend.get_all()
        assert len(all_mem) == 2  # Both entries kept
        
    def test_no_reconciliation(self):
        """Verify append-only doesn't reconcile superseded facts."""
        backend = AppendOnlyBackend()
        backend.remember("CTR-0001", {"action": "create", "data": {"counterparty": "Acme Corp", "value_usd": 100000}})
        backend.remember("CTR-0001", {"action": "terminate", "data": {"reason": "mutual_agreement"}})
        all_mem = backend.get_all()
        # Both create and terminate entries exist
        actions = [e["action"] for e in all_mem]
        assert "create" in actions
        assert "terminate" in actions


class TestRecentWindowBackend:
    """Test the sliding window baseline."""
    
    def test_window_size(self):
        backend = RecentWindowBackend(window_size=3)
        for i in range(5):
            backend.remember(f"CTR-{i}", {"action": "create", "data": {"counterparty": "Acme Corp"}})
        all_mem = backend.get_all()
        assert len(all_mem) == 3  # Only last 3
        
    def test_forgets_old(self):
        backend = RecentWindowBackend(window_size=5)
        for i in range(10):
            backend.remember(f"CTR-{i}", {"action": "create", "data": {"counterparty": f"Corp{i}"}})
        all_mem = backend.get_all()
        # CTR-0 through CTR-4 should be gone
        cids = [m["contract_id"] for m in all_mem]
        assert "CTR-0" not in cids
        assert "CTR-9" in cids


class TestBenchmarkIntegration:
    """Integration test: run the full benchmark."""
    
    def test_full_benchmark(self):
        from run_benchmark import run_benchmark
        
        # Run with temporary output files
        with tempfile.TemporaryDirectory() as tmpdir:
            json_out = os.path.join(tmpdir, "results.json")
            md_out = os.path.join(tmpdir, "results.md")
            
            results = run_benchmark(json_out, md_out)
            
            # Verify results
            assert "active_digest" in results
            assert "append_only" in results
            assert "recent_window" in results
            
            # Verify JSON output
            with open(json_out) as f:
                data = json.load(f)
            assert "summary" in data
            assert len(data["summary"]) == 3
            
            # Verify markdown output
            with open(md_out) as f:
                md = f.read()
            assert "Contract Reconciliation" in md
