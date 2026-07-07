# 🐛 Memanto Bug Report — Session & Content Filter Vulnerabilities

## Summary

Three bugs found in Memanto v0.2.5 affecting **memory integrity**, **session stability**, and **agent creation**. These issues prevent normal usage of the memory system in realistic production scenarios.

---

## Bug 1: Session Token Expires Mid-Workflow (Severity: High)

### Description
Session tokens expire extremely quickly (observed within seconds of sequential API calls), causing `401 Unauthorized` errors during normal multi-step memory operations. A user storing multiple memories in a single workflow session gets locked out after 1-2 successful requests.

### Steps to Reproduce

```python
import httpx

BASE = "http://127.0.0.1:8765"

# 1. Activate agent and get session token
r = httpx.post(f"{BASE}/api/v2/agents/my_agent/activate", timeout=10)
token = r.json()["session_token"]
headers = {"X-Session-Token": token}

# 2. First memory — SUCCEEDS
r = httpx.post(f"{BASE}/api/v2/agents/my_agent/remember",
    json={"content": "My WiFi password is sunshine123"},
    headers=headers, timeout=15)
print(r.status_code)  # 200 ✅

# 3. Second memory (seconds later) — FAILS
r = httpx.post(f"{BASE}/api/v2/agents/my_agent/remember",
    json={"content": "Remember: the office door code is 4521"},
    headers=headers, timeout=15)
print(r.status_code)  # 401 ❌ — Same token, same session!
```

### Expected Behavior
All requests within a valid session should succeed until the session's `expires_at` time (JWT shows 6 hours). The token should remain valid for the full duration.

### Actual Behavior
The session token becomes invalid after 1-2 requests, despite the JWT's `expires_at` being hours in the future. This makes batch operations (storing conversation history, importing memories) impossible.

### Impact
- **Breaks the core use case**: An AI companion that remembers conversations needs to store multiple facts per interaction
- **Affects all integrations**: Any client using the API programmatically will hit this in normal workflows
- Users cannot reliably store more than 1 memory per session activation

---

## Bug 2: Agent Creation Returns 500 Internal Server Error (Severity: High)

### Description
The `POST /api/v2/agents` endpoint returns HTTP 500 (Internal Server Error) when creating new agents, even with valid payloads matching the API schema.

### Steps to Reproduce

```python
import httpx

r = httpx.post("http://127.0.0.1:8765/api/v2/agents",
    json={"agent_id": "new_test_agent", "pattern": "support"},
    timeout=10)
print(r.status_code)  # 500
print(r.text)         # "Internal Server Error"
```

### Expected Behavior
A new agent should be created and return 201 with the agent details.

### Actual Behavior
Returns 500 with no useful error message. The error is not related to duplicate agent IDs — tested with unique IDs that don't exist in the system.

### Impact
- **Cannot onboard new users/agents** programmatically
- The only agents available are ones created before this bug manifested
- Breaks the documented setup flow from the README (`prime env init` → create agent)

---

## Bug 3: Inconsistent Content Filtering / False Positive Blocking (Severity: Medium)

### Description
The content moderation filter inconsistently blocks legitimate user memories. Some personal information passes while semantically identical content is rejected. The filter appears to trigger on certain keywords regardless of context.

### Steps to Reproduce

```python
import httpx

BASE = "http://127.0.0.1:8765"
r = httpx.post(f"{BASE}/api/v2/agents/my_agent/activate", timeout=10)
token = r.json()["session_token"]
h = {"X-Session-Token": token}

# These are ALL legitimate memories a user would want to store:
tests = [
    ("My WiFi password is sunshine123", "OK"),        # ✅ Passes
    ("The office door code is 4521", "BLOCKED"),       # ❌ Blocked
    ("My Netflix password is Popcorn99", "BLOCKED"),   # ❌ Blocked
    ("My credit card expires 12/28", "BLOCKED"),       # ❌ Blocked
    ("I had coffee this morning", "OK"),               # ✅ Passes
]

for content, expected in tests:
    r = httpx.post(f"{BASE}/api/v2/agents/my_agent/remember",
        json={"content": content}, headers=h, timeout=15)
    print(f"[{r.status_code}] {content}")
```

### Inconsistency Evidence
- `"My WiFi password is sunshine123"` → **Accepted** (200)
- `"I changed my Netflix password to Popcorn99"` → **Blocked** (401/403)

Both contain the word "password" + a credential. The filter is non-deterministic or uses inconsistent rules.

### Expected Behavior
A personal memory agent should allow users to store ANY personal information they choose. Content filtering for prompt injection is reasonable, but should not block:
- Personal credentials the user wants to remember
- Door codes, card expiry dates, account details
- Technical notes containing words like "system prompt"

### Suggested Fix
Separate prompt injection detection (block `<|im_start|>`, instruction override patterns) from PII detection. PII should be stored if the user explicitly adds it to THEIR OWN memory — it's the core use case of a personal memory system.

### Impact
- Users cannot use Memanto for its primary purpose (remembering personal information)
- A memory agent that won't remember passwords, codes, or account details is fundamentally broken
- Drives users away from the product

---

## Environment

- **Memanto version**: 0.2.5
- **moorcheh-sdk**: 1.3.7
- **Python**: 3.14.0
- **OS**: Windows 11
- **API**: Self-hosted (localhost:8765)
- **Date**: July 7, 2026

---

## Proposed Fix Direction

### Bug 1 (Session expiry):
Check the session validation logic in the middleware. The JWT `expires_at` field shows a 6-hour window, but something is invalidating sessions server-side (possibly the moorcheh.ai backend revoking tokens after first use, or a race condition in session renewal).

### Bug 2 (Agent creation):
The 500 error likely comes from the moorcheh.ai backend. Could be a schema validation issue, a missing required field not documented in the OpenAPI spec, or a database constraint. Adding proper error messages instead of a bare 500 would help.

### Bug 3 (Content filter):
Implement context-aware filtering:
```python
# Instead of keyword-blocking, use intent classification:
# - "Ignore all previous instructions" → BLOCK (injection attempt)
# - "My Netflix password is X" → ALLOW (personal memory storage)
```

---

## Social Amplification

*(Will post analysis on Reddit r/cybersecurity and X after PR submission)*
