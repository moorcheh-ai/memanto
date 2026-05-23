# LangGraph + Memanto: Customer Support Agent with Persistent Memory

A LangGraph-powered **customer support agent** that uses **Memanto** as its long-term memory layer — giving your support graph a permanent brain that remembers customers, issues, and resolutions across sessions.

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  LangGraph Customer Support Workflow                            │
│                                                                  │
│  ┌─────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────┐  │
│  │ TRIAGE  │─▶│ INVESTIGATE  │─▶│ RESOLVE  │─▶│ FOLLOW_UP  │  │
│  │ classify│  │ search+recall│  │  apply   │  │  commit    │  │
│  └────┬────┘  └──────┬───────┘  └────┬─────┘  └─────┬──────┘  │
│       │              │               │              │          │
│       │         ┌────▼────┐     ┌───▼────┐    ┌────▼────┐    │
│       │         │ MEMANTO │     │MEMANTO │    │ MEMANTO │    │
│       │         │ recall  │     │remember│    │commit   │    │
│       │         │ history │     │resolve │    │ memory  │    │
│       │         └─────────┘     └────────┘    └─────────┘    │
│       │                                                        │
│  ┌───▼────┐                                                    │
│  │MEMANTO │  Remember customer issue for future sessions      │
│  │remember│                                                    │
│  └────────┘                                                    │
└──────────────────────────────────────────────────────────────────┘
```

## ✨ What This Demonstrates

### 🧠 Cross-Session Recall (The Key Feature)
If Customer A reports a payment bug on Monday, and Customer B reports the same issue on Tuesday, the agent **remembers** Monday's resolution because it's stored in Memanto — not in the ephemeral LangGraph state.

### 📋 4-Node Workflow
1. **TRIAGE**: Classify ticket severity/category + recall customer history from Memanto
2. **INVESTIGATE**: Search for similar past issues in Memanto + store findings as new memories
3. **RESOLVE**: Generate resolution enriched with recalled solutions + store resolution as high-confidence memory
4. **FOLLOW_UP**: Send follow-up message + store commitment memory for high-severity tickets

### 🔒 Typed Semantic Memory
- **event** — Customer interactions and ticket submissions
- **fact** — Resolutions and root causes
- **learning** — Investigation findings and workarounds
- **instruction** — Recommended actions
- **observation** — Customer behavior patterns
- **commitment** — Follow-up promises for high-severity tickets
- **preference** — Customer communication preferences

## 🎬 Demo: Cross-Session Recall

### Session 1 (Monday): Customer reports a payment issue

```bash
python run_agent.py --customer cust-123 --message "My payment keeps failing with a timeout error"
```

```
🎫 Ticket TKT-0001 from cust-123
💬 "My payment keeps failing with a timeout error"
────────────────────────────────────────
📊 Triage: HIGH / billing

✅ Resolution:
1. Root cause: Payment gateway connection pool was exhausted.
2. Resolution: Increased pool size from 10 to 50 connections.
3. Prevention: Added auto-scaling for connection pool.

📩 Follow-up:
Hi there! We've resolved your payment timeout issue...
```

### Session 2 (Tuesday): Different customer, same issue

```bash
python run_agent.py --customer cust-456 --message "Getting timeout when trying to pay"
```

```
🎫 Ticket TKT-0002 from cust-456
💬 "Getting timeout when trying to pay"
────────────────────────────────────────
📊 Triage: HIGH / billing
🔍 Found 2 similar past issues:
   - [FACT] Resolved payment timeout by increasing connection pool...

✅ Resolution:
Based on a previous resolution from yesterday: The payment timeout was
caused by an exhausted connection pool. We increased it from 10 to 50.
Since this is recurring, we're adding a health check monitor...
```

**The agent explicitly references the previous session's resolution** — that's the permanent brain in action.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An OpenAI API key

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

### Run

```bash
# Process a single ticket
python run_agent.py --customer cust-123 --message "My payment failed"

# Interactive mode (process multiple tickets)
python run_agent.py
```

### Test

```bash
python -m pytest test_integration.py -v
```

## 🧪 Test Evidence

```
$ python -m pytest test_integration.py -v
==================== test session starts ====================
test_integration.py::TestCustomerSupportAgent::test_triage_classifies_billing_issue PASSED
test_integration.py::TestCustomerSupportAgent::test_cross_session_recall PASSED
test_integration.py::TestCustomerSupportAgent::test_similar_issues_recalled PASSED
test_integration.py::TestCustomerSupportAgent::test_resolution_is_stored_in_memory PASSED
test_integration.py::TestCustomerSupportAgent::test_high_severity_creates_commitment PASSED
test_integration.py::TestCustomerSupportAgent::test_complete_workflow_produces_all_outputs PASSED
test_integration.py::TestCrossSessionRecallIsolation::test_memories_persist_across_independent_graphs PASSED
==================== 7 passed in 0.12s ====================
```

## 🔑 Why This Matters

LangGraph's built-in state is **ephemeral** — it exists only within a single graph execution. When the graph finishes, the state is gone. This means:

- ❌ Can't remember what happened yesterday
- ❌ Can't share knowledge between different agent instances
- ❌ Can't build on previous resolutions

Memanto fixes this by being the **persistent memory layer** outside the graph:

- ✅ Remembers customer issues from previous sessions
- ✅ Recalls resolutions from any past session
- ✅ Stores commitments and preferences permanently
- ✅ Enables any agent instance to access the same knowledge

## 📁 File Structure

```
langgraph-customer-support/
├── README.md              # This file
├── .env.example           # Environment template
├── requirements.txt       # Python dependencies
├── agent.py               # LangGraph workflow (4 nodes)
├── memanto_tool.py        # Memanto integration tool
├── run_agent.py           # CLI entry point
└── test_integration.py    # Integration tests
```

## 📜 License

MIT
