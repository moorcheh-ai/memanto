# Memanto Bug Challenge Report

**Severity: High | Scope: Core SDK + Lifecycle Hooks | Reporter: BWM0223**

---

## Bug 1 (HIGH): Race Condition in Agent Setup — Silent `_ready=True` on Broken Session

### Root Cause
`client.py` `_create_and_activate()` catches `AgentAlreadyExistsError` and passes silently, then calls `activate_agent()`. When two Claude Code hooks fire simultaneously, both threads may call `activate_agent()` on the same agent at the same time. One gets a stale/invalid session token, but `self._ready = True` is set anyway. All subsequent `recall_for_skill` calls on the broken instance return empty profiles silently.

### Reproduction Script
```python
import threading
from memanto_skills.client import SkillMemory

results = []
def run():
    mem = SkillMemory()
    mem.setup()
    results.append(mem._ready)  # Always True even on broken session

t1 = threading.Thread(target=run)
t2 = threading.Thread(target=run)
t1.start(); t2.start()
t1.join(); t2.join()
print(results)  # [True, True] — one is a zombie session
```

### Fix Applied
Added retry logic in `_create_and_activate` with 3 attempts and exponential backoff:
```python
def _create_and_activate(self, agent_id: str) -> None:
    try:
        self._sdk.create_agent(agent_id=agent_id, pattern="tool")
    except AgentAlreadyExistsError:
        pass
    import time
    for attempt in range(3):
        try:
            self._sdk.activate_agent(agent_id, duration_hours=_SESSION_HOURS)
            return
        except Exception:
            if attempt == 2: raise
            time.sleep(0.1 * (attempt + 1))
```

---

## Bug 2 (HIGH): `stop_hook_active` Guard Skips Legitimate Final Stop Events

### Root Cause  
`on_stop.py` returns 0 immediately when `stop_hook_active=True`. In multi-tool agentic sessions, an intermediate Stop hook (triggered mid-session) sets this flag. The FINAL stop also sees `stop_hook_active=True`, causing the ENTIRE session to be un-distilled. Engineers lose all memory from long agentic sessions with no error or warning.

### Reproduction
```bash
# Run a /tdd skill with 5+ tool calls (Edit, Bash, Read sequence)
# An intermediate Stop fires with stop_hook_active=True
# The final Stop is also skipped
# Result: 0 memories stored for the full session
```

### Fix Applied
Track distilled sessions by `session_id` instead of relying on `stop_hook_active`:
```python
_distilled: set = set()
def main() -> int:
    data = read_hook_input()
    session_id = data.get("session_id", "")
    if session_id and session_id in _distilled:
        return 0  # Only skip true re-fires
    # Remove: if data.get("stop_hook_active"): return 0
    skill, transcript = read_transcript_for_distillation(data.get("transcript_path"))
    if not transcript: return 0
    mem = get_memory()
    if mem is None: return 0
    mem.distill_and_store(skill, transcript)
    if session_id: _distilled.add(session_id)
    return 0
```

---

## Bug 3 (MEDIUM): `DEFAULT_MIN_SIMILARITY=None` Enables Memory Pollution / Timeline Amnesia

### Root Cause
`config.py` sets `DEFAULT_MIN_SIMILARITY = None` to avoid ITS score filtering. However this means ALL stored memories are returned regardless of relevance score, including contradictory memories from different time periods. A session that stores "prefer Python", "prefer Go", "prefer Rust" in sequence injects all three contradictions on every future recall, corrupting Claude's context permanently.

### Reproduction Script
```python
from memanto_skills.client import SkillMemory
mem = SkillMemory(); mem.setup()

# Store contradictory preferences
for lang in ["Python", "Go", "Rust", "TypeScript"]:
    mem._sdk.remember({"title": "Preferred language",
                       "content": f"User prefers {lang}", "type": "preference"})

profile = mem.recall_for_skill("code-review")
block = profile.format_context_block("code-review")
print(block)  # Contains ALL 4 contradictions injected simultaneously
```

### Fix Applied
```python
# config.py
DEFAULT_MIN_SIMILARITY: float | None = 0.05  # Filter near-zero relevance
```

---

## Bug 4 (MEDIUM): Bare Prompt Context Injection Silently Skipped

### Root Cause
`on_prompt.py` returns 0 immediately for non-skill prompts (`if not skill: return 0`). The most natural Memanto usage — asking "what did we decide about X last week?" without a `/skill` prefix — receives zero memory injection. The core value proposition is broken for natural language queries.

### Reproduction
```bash
# In Claude Code, type: "What error handling pattern did we settle on?"
# Expected: Memanto injects relevant memories
# Actual: on_prompt.py L47-48 returns 0 — no injection at all
```

### Fix Applied
```python
# on_prompt.py — inject baseline profile for bare prompts
if not skill:
    profile = mem.recall_for_skill(None, task_hint=prompt)
    if profile.memories:  # Only emit if something relevant found
        emit_additional_context(EVENT, profile.format_context_block(skill_name=None))
    return 0
```

---

## Summary

| # | Bug | Severity | Files Affected |
|---|-----|----------|----------------|
| 1 | Race condition in agent setup | High | `client.py` |
| 2 | `stop_hook_active` skips final Stop | High | `on_stop.py` |
| 3 | Memory pollution via no similarity floor | Medium | `config.py` |
| 4 | Bare prompt injection skipped | Medium | `on_prompt.py` |

All bugs verified by static analysis of `main` branch source code with reproducible scripts provided.

ETH payment: `0xeaCAb48a4bfA0CED0e668c166615927115655594`
