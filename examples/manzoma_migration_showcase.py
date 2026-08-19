
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure we can import memanto
sys.path.append(str(Path(__file__).parent.parent))

from memanto.cli.migrate.runner import run_migration
from memanto.cli.migrate.okf_loader import load_okf_bundle
from unittest.mock import MagicMock

def run_manzoma_freedom_showcase():
    """
    SHOWCASE: The Manzoma Freedom Loop 🦋
    
    Scenario: A retail business in Egypt (Manzoma ERP) wants to migrate 
    memories for 3 different branches (Alpha, Beta, Gamma) into Memanto 
    without losing agent context.
    """
    print("🚀 Starting Manzoma -> Memanto Multi-Agent Migration Showcase")
    
    # 1. Setup simulated Manzoma data in OKF format
    showcase_dir = Path("./manzoma_showcase")
    showcase_dir.mkdir(exist_ok=True)
    
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
    
    print(f"✅ Prepared OKF bundle with {len(branches)} agent-specific memories.")

    # 2. Run Migration using our new Multi-Agent logic
    mock_client = MagicMock()
    mock_client.batch_remember.return_value = {"results": [], "successful": 1, "failed": 0}
    
    print("📦 Executing Multi-Agent Migration...")
    
    # Load the bundle
    bundle = load_okf_bundle(showcase_dir)
    
    # Run the migration (this uses our patched runner.py)
    summary, rows = run_migration(
        provider="okf",
        export=bundle,
        client=mock_client,
        agent_id="default_fallback",
        dry_run=False,
        on_progress=print
    )
    
    # 3. Verification
    print("\n--- 📊 Migration Summary ---")
    print(f"Total Batches: {summary.batches}")
    print(f"Successful Imports: {summary.imported}")
    
    # Verify that the client was called for each specific agent_id from the OKF frontmatter
    called_agents = [call.kwargs['agent_id'] for call in mock_client.batch_remember.call_args_list]
    print(f"Targeted Agents: {called_agents}")
    
    if set(called_agents) == set(branches.keys()):
        print("\n🏆 SUCCESS: All Manzoma branches migrated to their respective Memanto Agents!")
        print("Proof of the 'Freedom Loop': Data -> OKF -> Multi-Agent Memanto.")
    else:
        print("\n❌ Error: Migration failed to preserve agent isolation.")

    # Cleanup
    for f in showcase_dir.glob("*.md"): f.unlink()
    showcase_dir.rmdir()

if __name__ == "__main__":
    run_manzoma_freedom_showcase()
