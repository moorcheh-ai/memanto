"""
Synthetic B2B contract lifecycle dataset for contract reconciliation memory benchmark.

Each entry tracks:
- Contract ID
- Signed date
- Counterparty
- Active status
- Key obligations (list)
- Payment terms
- Metadata (auto-computed)
"""
import json
from datetime import datetime, timedelta
import random


def generate_dataset(seed: int = 42) -> list:
    random.seed(seed)

    counterparties = [
        "Acme Corp", "Beta LLC", "Gamma Inc", "Delta Partners", "Epsilon Ltd",
        "Zeta Group", "Eta Technologies", "Theta Services", "Iota Systems",
        "Kappa Ventures"
    ]

    contracts = []
    for i in range(1, 31):
        signed_date = datetime(2026, 1, 1) + timedelta(days=random.randint(0, 120))
        n_obligations = random.randint(2, 8)
        obligations = [
            f"Obligation {j}: deliver {'Phase ' + str(random.randint(1,5))} by {'Q' + str(random.randint(1,4))} 2026"
            for j in range(1, n_obligations + 1)
        ]

        contracts.append({
            "contract_id": f"CTR-{i:04d}",
            "counterparty": random.choice(counterparties),
            "signed_date": signed_date.strftime("%Y-%m-%d"),
            "value_usd": random.randint(10000, 500000),
            "active": random.choice(["active", "active", "active", "terminated", "paused"]),
            "obligations": obligations,
            "payment_terms": random.choice([
                "net_30", "net_45", "net_60", "milestone_50_50", "milestone_40_40_20"
            ])
        })

    return contracts


def generate_queries(contracts: list, seed: int = 42) -> list:
    """Generate golden queries with known expected answers."""
    random.seed(seed)

    queries = []
    active_contracts = [c for c in contracts if c["active"] == "active"]

    # Query type 1: All active contracts with obligation count > 4
    queries.append({
        "query_id": "Q001",
        "type": "filter",
        "description": "List active contracts with more than 4 obligations",
        "expected": [c["contract_id"] for c in contracts if c["active"] == "active" and len(c["obligations"]) > 4]
    })

    # Query type 2: Total value of active contracts
    queries.append({
        "query_id": "Q002",
        "type": "aggregate",
        "description": "Total USD value of all active contracts",
        "expected": sum(c["value_usd"] for c in contracts if c["active"] == "active")
    })

    # Query type 3: Counterparty with most contracts
    from collections import Counter
    cp_counts = Counter(c["counterparty"] for c in contracts if c["active"] == "active")
    top_cp = cp_counts.most_common(1)[0][0] if cp_counts else None
    queries.append({
        "query_id": "Q003",
        "type": "groupby",
        "description": f"Counterparty with most active contracts (expect: {top_cp})",
        "expected": top_cp
    })

    # Query type 4: Contracts with milestone payments
    milestone_contracts = [c["contract_id"] for c in contracts if "milestone" in c["payment_terms"] and c["active"] == "active"]
    queries.append({
        "query_id": "Q004",
        "type": "filter",
        "description": "Active contracts with milestone payment terms",
        "expected": milestone_contracts
    })

    # Query type 5: Termination check
    terminated = [c["contract_id"] for c in contracts if c["active"] == "terminated"]
    queries.append({
        "query_id": "Q005",
        "type": "filter",
        "description": "Terminated contract IDs",
        "expected": terminated
    })

    return queries


def generate_memory_log(contracts: list) -> list:
    """
    Generate a timeline of memory updates simulating contract lifecycle changes.
    Each update represents an agent memory event (remember/store).
    """
    memories = []
    base_date = datetime(2026, 1, 1)

    # Initial state: all contracts created
    for c in contracts:
        memories.append({
            "timestamp": base_date + timedelta(days=10),
            "action": "create",
            "contract_id": c["contract_id"],
            "data": {
                "counterparty": c["counterparty"],
                "value_usd": c["value_usd"],
                "payment_terms": c["payment_terms"],
                "obligations": c["obligations"]
            }
        })

    # Update: Some contracts terminated
    for c in contracts:
        if c["active"] == "terminated":
            memories.append({
                "timestamp": base_date + timedelta(days=100),
                "action": "terminate",
                "contract_id": c["contract_id"],
                "data": {"reason": "mutual_agreement", "effective_date": "2026-05-01"}
            })

    # Update: Some contracts paused
    for c in contracts:
        if c["active"] == "paused":
            memories.append({
                "timestamp": base_date + timedelta(days=80),
                "action": "pause",
                "contract_id": c["contract_id"],
                "data": {"reason": "force_majeure", "effective_date": "2026-04-01"}
            })

    # Update: Obligation changes for some
    for c in contracts[:5]:
        if c["active"] == "active":
            memories.append({
                "timestamp": base_date + timedelta(days=60),
                "action": "update_obligations",
                "contract_id": c["contract_id"],
                "data": {
                    "new_obligation": f"Added milestone deliverable Q3 2026",
                    "total_obligations": len(c["obligations"]) + 1
                }
            })

    # Sort by timestamp
    memories.sort(key=lambda m: m["timestamp"])
    return memories
