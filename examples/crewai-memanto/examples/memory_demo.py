#!/usr/bin/env python3
"""
examples/memory_demo.py  –  CrewAI + Memanto Cross-Session Memory Demo

TWO modes:
  --mock   Fully offline, no server needed. RECORD THIS for Asciinema.
  (live)   Connects to real Memanto server (requires: memanto serve)

Usage:
    python examples/memory_demo.py --mock          # offline/recording
    python examples/memory_demo.py --api-key mk-.. # real Memanto
"""

import argparse, os, sys, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DIVIDER = "─" * 60

def step(n, title):
    print(f"\n{DIVIDER}\n  STEP {n}: {title}\n{DIVIDER}")

# ── Mock (offline) ─────────────────────────────────────────────────────────────

class MockMem:
    def __init__(self): self._db = {}
    def store(self, content, memory_type="fact", tags=None, metadata=None):
        mid = f"mem_{uuid.uuid4().hex[:8]}"
        self._db[mid] = {"id": mid, "content": content, "type": memory_type, "score": 0.97}
        return self._db[mid]
    def search(self, query, limit=5, memory_type=None):
        r = [v for v in self._db.values() if not memory_type or v["type"] == memory_type]
        return r[:limit]
    def answer(self, q):
        mems = list(self._db.values())
        return f"Based on {len(mems)} stored memories: {mems[0]['content'][:100]}... [RAG]" if mems else "No memories."
    def update(self, mid, new_content, metadata=None):
        if mid in self._db:
            self._db[mid]["metadata"] = {"previous_content": self._db[mid]["content"], "correction": True}
            self._db[mid]["content"] = new_content
        return self._db.get(mid, {"id": mid, "content": new_content})

class MockCrewMem:
    def __init__(self): self._m = MockMem()
    def store_finding(self, content, agent, tags=None):
        return self._m.store(content, "fact", (tags or []) + [agent])
    def recall_findings(self, query, limit=5):
        return [{"id": r["id"], "memory": r["content"], "score": r["score"]}
                for r in self._m.search(query, limit, "fact")]
    def answer(self, q): return self._m.answer(q)
    def correct_memory(self, memory_id, new_fact): return self._m.update(memory_id, new_fact)

# ── Demo ───────────────────────────────────────────────────────────────────────

def run_demo(mem, mock_mode):
    print(f"\n  Mode: {'🟡 MOCK (offline — safe to record)' if mock_mode else '🟢 LIVE (Memanto server)'}")

    step(1, "ResearchAgent stores findings  [Session A]")
    findings = [
        ("Python 3.12 'perf' mode speeds up CPython by ~5%.",            ["python","performance"]),
        ("LLM-assisted code review cuts bug escape rate by ~30% (2024).", ["llm","code-review"]),
        ("GitHub Copilot used by 1.8M developers as of Q1 2025.",         ["copilot","adoption"]),
        ("AI developer tools market will reach $12B by 2027.",            ["market","forecast"]),
    ]
    stored_ids = []
    for content, tags in findings:
        r = mem.store_finding(content=content, agent="ResearchAgent", tags=tags)
        mid = r.get("id","N/A"); stored_ids.append(mid)
        print(f"  ✅ Stored [{mid}]"); print(f"     {content}"); time.sleep(0.35)
    print(f"\n  📦 {len(stored_ids)} findings saved to Memanto namespace.")

    step(2, "Session boundary  [new process / 24 hours later]")
    for i in range(3): print(f"  💤  {'.' * (i+1)}", end="\r"); time.sleep(0.6)
    print("  ✅  New session. ResearchAgent memories persist in Memanto.     ")

    step(3, "WriterAgent recalls from Memanto  [Session B — different run]")
    for q in ["Python performance", "AI tools developer impact", "market size forecast"]:
        print(f"\n  🔍 recall_memory('{q}')")
        for r in mem.recall_findings(query=q, limit=2):
            print(f"     [{r['id']}] score={r.get('score',0):.2f}  {r['memory'][:88]}…")
        time.sleep(0.45)

    step(4, "WriterAgent: RAG answer over stored memories")
    q = "What is the current state of AI developer tools?"
    print(f"  ❓ {q}"); time.sleep(0.5)
    print(f"\n  🧠 {mem.answer(q)}")

    step(5, "Correcting a contradictory memory  [bonus: conflict resolution]")
    tid = next((i for i in stored_ids if i != "N/A"), None)
    if tid:
        old = "GitHub Copilot used by 1.8M developers as of Q1 2025."
        new = "GitHub Copilot surpassed 2.3M developers as of Q2 2025 (updated)."
        print(f"  ⚠️  Outdated: {old}")
        print(f"  🔄 Correcting [{tid}]…"); time.sleep(0.5)
        mem.correct_memory(memory_id=tid, new_fact=new)
        print(f"  ✅ Updated:  {new}")
        print(f"     └─ metadata.previous_content = old fact  ← audit trail intact")
        results = mem.recall_findings("GitHub Copilot developers", limit=1)
        if results:
            print(f"\n  🔍 Re-recall confirms correction:")
            print(f"     {results[0]['memory'][:110]}…")
    else:
        print("  (skipped — no valid ID)")

    print(f"\n{DIVIDER}")
    print("  ✨  Demo complete!")
    print("  💾 Findings persist across sessions — WriterAgent can recall them anytime.")
    if mock_mode:
        print("  📝 MOCK mode: run without --mock + 'memanto serve' for real persistence.")
    print(f"{DIVIDER}\n")

# ── Entry ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock",      action="store_true", help="Offline mode, no server needed")
    p.add_argument("--url",       default=os.getenv("MEMANTO_BASE_URL","http://127.0.0.1:8000"))
    p.add_argument("--api-key",   default=os.getenv("MOORCHEH_API_KEY",""))
    p.add_argument("--namespace", default="crewai-memory-demo")
    args = p.parse_args()

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║     CrewAI  +  Memanto  –  Cross-Session Memory Demo     ║")
    print("║   ResearchAgent stores  →  WriterAgent recalls later     ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if args.mock:
        mem = MockCrewMem()
    else:
        try:
            from memanto_bridge import MeMantoCrewMemory
            mem = MeMantoCrewMemory(base_url=args.url, api_key=args.api_key, agent_id=args.namespace)
        except Exception as exc:
            print(f"\n❌ Cannot connect to Memanto at {args.url}: {exc}")
            print("💡 Run 'memanto serve' first, or use --mock for offline demo.")
            sys.exit(1)

    run_demo(mem, mock_mode=args.mock)

if __name__ == "__main__":
    main()