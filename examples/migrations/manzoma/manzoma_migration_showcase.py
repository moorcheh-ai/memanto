
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Ensure we can import memanto
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from memanto.cli.migrate.runner import run_migration
from memanto.cli.migrate.okf_loader import load_okf_bundle

def run_manzoma_freedom_showcase():
    """
    SHOWCASE: The Manzoma Freedom Loop 🦋
    
    Scenario: A retail business in Egypt (Manzoma ERP) wants to migrate 
    memories for 3 different branches (Alpha, Beta, Gamma) into Memanto 
    without losing agent context.
    """
    print("🚀 Starting Manzoma -> Memanto Multi-Agent Migration Showcase")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        showcase_dir = Path(tmp_dir)
        
        branches = {
            "branch_alpha": "Branch in Damietta - Focus on high-volume furniture sales.",
            "branch_beta": "Branch in Cairo - Focus on tech gadgets and accessories.",
            "branch_gamma": "Branch in Alexandria - Focus on apparel and clothing."
        }
        
        for agent_id, context in branches.items():
            content = f"""---
type: observation
title: {agent_id} Market Context
agent_id: {agent_id}
tags: [manzoma, retail, egypt]
timestamp: {datetime.now(timezone.utc).isoformat()}
---
{context}
Inventory sync status: 100% Verified.
Total volume processed: $10,000.
"""
            (showcase_dir / f"{agent_id}.md").write_text(content)
        
        print(f"✅ Prepared OKF bundle with {len(branches)} agent-specific memories in temporary directory.")

        # 2. Setup a robust mock client that simulates agent isolation
        mock_client = MagicMock()
        mock_client.agent_id = "initial_agent"
        
        # Track "stored" memories per agent
        storage = {agent_id: [] for agent_id in branches.keys()}
        
        def mock_batch_remember(agent_id, memories):
            if agent_id not in storage:
                storage[agent_id] = []
            storage[agent_id].extend(memories)
            return {"results": [], "successful": len(memories), "failed": 0}
            
        def mock_activate_agent(agent_id):
            print(f"🔄 Client: Activating session for agent '{agent_id}'")
            mock_client.agent_id = agent_id
            return {"status": "active", "agent_id": agent_id}

        mock_client.batch_remember.side_effect = mock_batch_remember
        mock_client.activate_agent.side_effect = mock_activate_agent
        
        print("📦 Executing Multi-Agent Migration...")
        
        # Load the bundle
        bundle = load_okf_bundle(showcase_dir)
        
        # Run the migration
        summary, rows = run_migration(
            provider="okf",
            export=bundle,
            client=mock_client,
            agent_id="default_fallback",
            dry_run=False,
            on_progress=print
        )
        
        # 3. Verification of Round-Trip Fidelity and Agent Isolation
        print("\n--- 📊 Migration Verification ---")
        
        all_passed = True
        for agent_id, expected_context in branches.items():
            stored_memories = storage.get(agent_id, [])
            if len(stored_memories) == 1:
                stored_content = stored_memories[0]['content']
                if expected_context in stored_content:
                    print(f"✅ Agent '{agent_id}': Data verified and isolated.")
                else:
                    print(f"❌ Agent '{agent_id}': Data corruption detected!")
                    all_passed = False
            else:
                print(f"❌ Agent '{agent_id}': Expected 1 memory, found {len(stored_memories)}.")
                all_passed = False
        
        if all_passed:
            print("\n🏆 SHOWCASE SUCCESS: All Manzoma branches migrated with perfect isolation!")
            print("Proof of the 'Freedom Loop': Data -> OKF -> Multi-Agent Memanto.")
        else:
            print("\n❌ SHOWCASE FAILED: Verification errors found.")

if __name__ == "__main__":
    run_manzoma_freedom_showcase()
