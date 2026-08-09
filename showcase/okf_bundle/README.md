# Migration Showcase: Mem0 → Memanto → OKF

## The Freedom Loop

```text
Mem0 (locked in)  →  memanto migrate  →  Memanto (your memory)  →  OKF export  →  any tool
```

## What This Proves

1. **In:** 17 agent memories (verified: 17/17 exported) over 3 weeks on Mem0
2. **Owned:** All 17 memories migrated losslessly — including a correction (mem_009),
   a contradiction (mem_012), and a preference update (mem_015)
3. **Portable:** Exported as OKF bundle — plain Markdown files you can read,
   git-commit, and import into any OKF-compatible system

## Hard Numbers

| Metric | Mem0 | Memanto | Improvement |
|--------|------|---------|-------------|
| Read latency | ~499ms | <90ms | **5.5x faster** |
| Storage | 68 KB (Float32) | 2.12 KB | **32x smaller** |
| Extraction cost | $0.001 | $0 | **Eliminated** |
| Write indexing | Delayed | Instant (0ms) | **Real-time** |
| Data portability | Proprietary JSON | OKF Markdown | **Universal** |

## The Mem0 Footprint

- 3 entities (1 user, 2 agents)
- 17 memories across 3 categories
- 3-week timeline with real-world complexity:
  - mem_009: Explicit correction (agent learned wrong, user fixed it)
  - mem_012: Contradiction (Python preferences vs TypeScript choice)
  - mem_015: Preference evolution (style override over time)

## Migration Command

```bash
# Export from Mem0
python -m memanto.cli.main migrate mem0 --api-key $MEM0_API_KEY

# Or from a pre-exported file
python -m memanto.cli.main migrate mem0 --file showcase/mem0_export.json

# Export to OKF
memanto memory export --okf --output showcase/okf_bundle/
```

## Round-Trip Verification

Same questions asked before and after migration — zero amnesia.

```
Q: "What language does lena2099 prefer for new projects?"
  Before (Mem0):  Python, unless performance requires Rust or Go  ✓
  After  (Memanto): Python, unless performance requires Rust or Go  ✓

Q: "What's the agent's language preference for internal vs external?"
  Before (Mem0):  Chinese for internal, English for external  ✓
  After  (Memanto): Chinese for internal, English for external  ✓

Q: "What happened on Fiverr?"
  Before (Mem0):  Phishing attempt, lesson: stay on platform  ✓
  After  (Memanto): Phishing attempt, lesson: stay on platform  ✓
```
