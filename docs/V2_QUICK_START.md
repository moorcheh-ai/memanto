# MEMANTO Quick Start Guide

**5-Minute Guide to Session-Based API**

---

## Installation

```bash
pip install pyjwt pydantic-settings
```

## Basic Workflow

### 1. Create Agent (One-Time)

```bash
curl -X POST "http://localhost:8000/api/v2/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "pattern": "support",
    "description": "My first MEMANTO agent"
  }'
```

### 2. Activate Session

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/activate" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "session_id": "sess_abc123",
  "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "agent_id": "my-agent",
  "namespace": "memanto_agent_my-agent",
  "started_at": "2025-12-28T16:00:00Z",
  "expires_at": "2025-12-28T20:00:00Z",
  "status": "active"
}
```

**Save the `session_token`** - you'll need it for all operations!

### 3. Store Memory (NO tenant_id!)

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/remember" \
  -H "X-Session-Token: YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "This is my first memory",
    "type": "fact",
    "title": "First Memory",
    "confidence": 0.9,
    "tags": ["quick-start", "example"],
    "source": "agent",
    "provenance": "explicit_statement"
  }'
```

### 4. Upload a File (Optional)

Upload a document directly into the agent's memory — content is chunked and made searchable via `recall`.

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/upload-file" \
  -H "X-Session-Token: YOUR_SESSION_TOKEN" \
  -F "file=@/path/to/document.pdf"
```

**Response:**
```json
{
  "agent_id": "my-agent",
  "session_id": "sess_abc123",
  "namespace": "memanto_agent_my-agent",
  "file_name": "document.pdf",
  "file_size": 204800,
  "status": "uploaded",
  "message": "File uploaded successfully"
}
```

**Supported formats:** `.pdf`, `.docx`, `.xlsx`, `.json`, `.txt`, `.csv`, `.md`

### 5. Recall Memories

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/recall" \
  -H "X-Session-Token: YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "first memory",
    "limit": 5,
    "type": ["fact"]
  }'
```

### 6. Ask Questions (RAG)

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/answer" \
  -H "X-Session-Token: YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is my first memory?",
    "limit": 5,
    "temperature": 0.7,
    "ai_model": "anthropic.claude-sonnet-4-6",
    "kiosk_mode": true
  }'
```

`threshold` is only used when `kiosk_mode` is `true`. If omitted in kiosk mode, MEMANTO uses `0.10`.

---

## Python Example

```python
import httpx

# Configuration
AGENT_ID = "my-agent"
BASE_URL = "http://localhost:8000"

client = httpx.Client(base_url=BASE_URL)

# 1. Create agent (one-time)
create_response = client.post(
    "/api/v2/agents",
    json={
        "agent_id": AGENT_ID,
        "pattern": "support",
        "description": "Customer support agent"
    }
)
print("Agent created:", create_response.json())

# 2. Activate session
session_response = client.post(
    f"/api/v2/agents/{AGENT_ID}/activate"
)
session_data = session_response.json()
session_token = session_data["session_token"]
print(f"Session active until: {session_data['expires_at']}")

# 3. Headers for subsequent requests
headers = {
    "X-Session-Token": session_token
}

# 4. Store memories
memory = client.post(
    f"/api/v2/agents/{AGENT_ID}/remember",
    headers=headers,
    json={
        "type": "preference",
        "title": "Customer 123 Communication",
        "content": "Customer prefers email over phone",
        "confidence": 0.9,
        "tags": ["customer-123", "communication"],
        "source": "agent",
        "provenance": "explicit_statement"
    }
)
print("Memory stored:", memory.json())

# 5. Upload a file (optional)
with open("document.pdf", "rb") as f:
    upload = client.post(
        f"/api/v2/agents/{AGENT_ID}/upload-file",
        headers=headers,
        files={"file": ("document.pdf", f, "application/pdf")}
    )
print("Upload status:", upload.json()["status"])

# 7. Recall memories
memories = client.post(
    f"/api/v2/agents/{AGENT_ID}/recall",
    headers=headers,
    json={"query": "customer 123", "limit": 10}
)
print("Found memories:", len(memories.json()["memories"]))

# 8. Ask question
answer = client.post(
    f"/api/v2/agents/{AGENT_ID}/answer",
    headers=headers,
    json={"question": "How does customer 123 prefer to be contacted?"}
)
print("Answer:", answer.json()["answer"])
```

---

## Key Differences from V1

| Aspect | V1 (Deprecated) | V2 (Current) |
|--------|-----------------|--------------|
| **Authentication** | `?tenant_id=...` in query | Session token in header |
| **Setup** | None required | Create agent + activate session |
| **Security** | Query params (spoofable) | JWT tokens (signed) |
| **Namespace** | `memanto_{tenant}_agent_{id}` | `memanto_agent_{id}` |

---

## Session Management

### Check Session Status

```bash
curl -X GET "http://localhost:8000/api/v2/agents/my-agent/status" \
  -H "X-Session-Token: YOUR_SESSION_TOKEN"
```

### End Session

```bash
curl -X POST "http://localhost:8000/api/v2/agents/my-agent/deactivate"
```

---

## Agent Management

### List All Agents

```bash
curl -X GET "http://localhost:8000/api/v2/agents"
```

### Get Agent Info

```bash
curl -X GET "http://localhost:8000/api/v2/agents/my-agent"
```

### Delete Agent

```bash
curl -X DELETE "http://localhost:8000/api/v2/agents/my-agent"
```

---

## Error Handling

### Session Expired (401)

```python
try:
    response = client.post(url, headers=headers, params=params)
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        # Session expired - reactivate
        session_response = client.post(
            f"/api/v2/agents/{AGENT_ID}/activate"
        )
        session_token = session_response.json()["session_token"]
        # Retry with new token
```

### Agent Not Found (404)

```python
try:
    response = client.get(f"/api/v2/agents/{AGENT_ID}", headers=headers)
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        # Agent doesn't exist - create it
        client.post(
            "/api/v2/agents",
            json={"agent_id": AGENT_ID, "pattern": "support"}
        )
```

---

## Memory Types

- `fact` - Objective information
- `preference` - User/customer preferences
- `instruction` - Guidelines or rules
- `decision` - Past decisions with context
- `event` - Things that happened
- `goal` - Objectives or targets
- `commitment` - Promises or obligations
- `observation` - Noticed patterns
- `learning` - Lessons learned
- `relationship` - Connections between entities
- `context` - Background information
- `artifact` - Documents or outputs
- `error` - Mistakes or failures

---

## Agent Patterns

- `support` - Customer service, help desk
- `project` - Project management, task tracking
- `tool` - API integration, automation

---

## Best Practices

1. **Create agents once** - Store agent_id in your config
2. **Activate on startup** - Get session token when your app starts
3. **Auto-extend sessions** - Check expiration, extend if needed
4. **Handle 401 errors** - Reactivate session if it expires
5. **Use meaningful titles** - Makes memories easier to recall
6. **Tag appropriately** - Use tags for filtering
7. **Set realistic confidence** - 1.0 = certain, 0.5 = uncertain

---

## Next Steps

- **Full Documentation**: [SESSION_ARCHITECTURE.md](SESSION_ARCHITECTURE.md)
- **API Reference**: http://localhost:8000/docs

---

**That's it!** You're ready to use MEMANTO. No tenant_id required! 🎉
