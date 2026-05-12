# Getting Started with MEMANTO

**Audience**: Developers building AI agents who need persistent memory
**Time to complete**: 15-30 minutes
**Prerequisites**: Basic Python knowledge, Docker (optional)

---

## What is MEMANTO?

MEMANTO (Memory that AI Agents Love!) is a production-ready FastAPI service that gives your AI agents persistent memory across conversations, sessions, and workflows.

**Think of it as**: A PostgreSQL database, but optimized for AI agents - with semantic search, AI-powered summarization, and built specifically for agent workflows.

---

## Step 1: Get Moorcheh.ai Access

MEMANTO requires a Moorcheh.ai account for the underlying **no-indexing semantic database** and AI services.

**What makes Moorcheh unique**: Unlike traditional vector databases that use HNSW trees and approximate nearest neighbor (ANN) search, Moorcheh uses **Information Theoretic Vector Compression** with full vector scans and **ITS (Information Theoretic Score)** for exact, explainable semantic search. This eliminates indexing delays and enables instant memory availability - critical for real-time AI agent workflows.

**Key benefits for MEMANTO**:
- **Instant searchability**: Memories are available immediately after storage (no indexing wait)
- **Serverless architecture**: Scales effortlessly without state management
- **Deterministic results**: Same query always returns same results (not probabilistic)
- **80% cost savings**: More efficient than traditional vector databases
- **12ms context serving**: Fast enough for interactive AI conversations

**Cost & Free Tier**:
- **Start FREE**: 500 monthly credits = ~100,000 operations (no credit card required)
- **No idle costs**: True serverless - pay only for API calls, no infrastructure charges
- **No storage fees**: Cloud-native serverless architecture (AWS Lambda, Cloud Functions)
- **Enough for development**: Run multiple agents continuously on free tier
- **Scale affordably**: No base fees, pay only for operations beyond free tier

### Option A: Moorcheh Cloud (Recommended for Quick Start)

1. **Sign up for Moorcheh.ai**
   - Visit: https://moorcheh.ai
   - Create an account
   - Navigate to Dashboard → API Keys
   - Click "Create New API Key"
   - Copy your API key (starts with `mk_`)

2. **Save your API key securely**
   ```bash
   # Never commit this to git!
   export MOORCHEH_API_KEY="mk_your_api_key_here"
   ```

### Option B: Sovereign Moorcheh Cloud (Enterprise)

For enterprises requiring data sovereignty:

1. **Deploy Moorcheh to your VPC**
   - Contact Moorcheh.ai for sovereign cloud setup
   - Available on: AWS, Azure, GCP
   - Deploy using provided Terraform/CloudFormation templates
   - Get your private endpoint URL

2. **Configure MEMANTO for private deployment**
   ```bash
   export MOORCHEH_API_KEY="mk_your_private_key"
   export MOORCHEH_BASE_URL="https://moorcheh.your-company.internal"
   ```

**For this guide**, we'll use Option A (Moorcheh Cloud).

---

## Step 2: Deploy MEMANTO

You have 3 deployment options:

### Option 1: Docker (Recommended)

**Fastest way to get started:**

```bash
# 1. Clone the repository
git clone https://github.com/your-org/memanto.git
cd memanto

# 2. Create .env file with your Moorcheh API key
cat > .env << EOF
MOORCHEH_API_KEY=mk_your_api_key_here
ALLOWED_ORIGINS=*
LOG_LEVEL=INFO
EOF

# 3. Build and run with Docker
docker build -t memanto .
docker run -p 8000:8000 --env-file .env memanto

# 4. Verify it's running
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "service": "MEMANTO",
  "version": "1.0.0",
  "moorcheh_connected": true
}
```

### Option 2: Python (Development)

**For development and customization:**

```bash
# 1. Clone and setup
git clone https://github.com/your-org/memanto.git
cd memanto

# 2. Install Python dependencies (requires Python 3.8+)
pip install uv  # Modern Python package manager
uv sync         # Installs all dependencies

# Or use traditional pip
pip install -r requirements.txt

# 3. Create .env file
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY

# 4. Test Moorcheh connectivity
uv run python test_moorcheh.py

# 5. Start MEMANTO
uv run python app/main.py

# Or with auto-reload for development
uvicorn app.main:app --reload
```

### Option 3: Cloud Deployment

**For production:**

<details>
<summary><b>Deploy to AWS ECS/Fargate</b></summary>

```bash
# 1. Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URL
docker build -t memanto .
docker tag memanto:latest $ECR_URL/memanto:latest
docker push $ECR_URL/memanto:latest

# 2. Create ECS task definition
# Set environment variable: MOORCHEH_API_KEY

# 3. Deploy to ECS service
aws ecs update-service --cluster memanto-cluster --service memanto-service --force-new-deployment
```
</details>

<details>
<summary><b>Deploy to Google Cloud Run</b></summary>

```bash
# 1. Build and push to GCR
gcloud builds submit --tag gcr.io/PROJECT_ID/memanto

# 2. Deploy with secrets
gcloud run deploy memanto \
  --image gcr.io/PROJECT_ID/memanto \
  --platform managed \
  --region us-central1 \
  --set-secrets=MOORCHEH_API_KEY=moorcheh-key:latest
```
</details>

<details>
<summary><b>Deploy to Azure Container Instances</b></summary>

```bash
# 1. Build and push to ACR
az acr build --registry myregistry --image memanto .

# 2. Deploy to ACI
az container create \
  --resource-group myResourceGroup \
  --name memanto \
  --image myregistry.azurecr.io/memanto:latest \
  --environment-variables MOORCHEH_API_KEY=$MOORCHEH_API_KEY \
  --ports 8000
```
</details>

---

## Step 3: Verify Your MEMANTO Deployment

### Test the Health Endpoint

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "service": "MEMANTO",
  "moorcheh_connected": true
}
```

### Explore the Interactive API Documentation

Open your browser to:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You'll see all 17 API endpoints with interactive testing!

### Test a Basic Memory Operation

**Using the simplified agent API (recommended):**
 
 ```bash
 # 1. Activate agent session
 curl -X POST "http://localhost:8000/api/v2/agents/my-agent/activate" \
   -H "Content-Type: application/json"
 
 # 2. Save the session_token from response, then store memory
 curl -X POST "http://localhost:8000/api/v2/agents/my-agent/remember" \
   -H "X-Session-Token: YOUR_SESSION_TOKEN" \
   -H "Content-Type: application/json" \
   -d '{
     "type": "fact",
     "title": "Test Memory",
     "content": "MEMANTO is working",
     "confidence": 1.0,
     "source": "agent",
     "provenance": "explicit_statement"
   }'
 ```
 
 **Expected response:**
 ```json
 {
   "memory_id": "mem_abc123xyz",
   "agent_id": "my-agent",
   "namespace": "memanto_agent_my-agent",
   "status": "queued"
 }
 ```
 
 **Then recall the memory:**
 ```bash
 # Agent recalls its memories
 curl -X POST "http://localhost:8000/api/v2/agents/my-agent/recall" \
   -H "X-Session-Token: YOUR_SESSION_TOKEN" \
   -H "Content-Type: application/json" \
   -d '{
     "query": "MEMANTO",
     "limit": 5,
     "type": ["fact"]
   }'
 ```

**Expected response:**
```json
{
  "agent_id": "my-agent",
  "query": "MEMANTO",
  "temporal_filter": null,
  "memories": [
    {
      "id": "mem_abc123xyz",
      "title": "Test Memory",
      "content": "MEMANTO is working",
      "type": "fact",
      "confidence": 1.0,
      "created_at": "2025-12-28T10:30:00Z"
    }
  ]
}
```

**Congratulations!** 🎉 Your MEMANTO instance is running.

---

## Step 4: Integrate MEMANTO into Your AI Agent

Now that MEMANTO is running, you need to connect your AI agent to it.

### Quick Integration Example

**Using the simplified agent API:**

```python
import httpx
import asyncio
import os

class MyAIAgent:
    def __init__(self):
        self.memanto_url = "http://localhost:8000"
        self.agent_id = "customer-support-bot"  # Stable agent identity
        self.session_token = None # Will be set after activation
        self.client = httpx.AsyncClient()

    async def activate_session(self):
        """Activate a new session for the agent."""
        response = await self.client.post(
            f"{self.memanto_url}/api/v2/agents/{self.agent_id}/activate"
        )
        response.raise_for_status()
        self.session_token = response.json().get("session_token")
        if not self.session_token:
            raise ValueError("Failed to get session token from activation response.")
        print(f"Session activated for agent {self.agent_id}. Session Token: {self.session_token}")
        return self.session_token

    async def remember(self, fact: str, memory_type: str = "fact"):
        """Store a memory - MEMANTO handles namespace automatically"""
        if not self.session_token:
            await self.activate_session() # Activate if not already active

        response = await self.client.post(
            f"{self.memanto_url}/api/v2/agents/{self.agent_id}/remember",
            json={
                "type": memory_type,
                "title": "Conversation Memory",
                "content": fact,
                "confidence": 0.9,
                "source": "agent",
                "provenance": "explicit_statement"
            },
            headers={
                "X-Session-Token": self.session_token
            }
        )
        return response.json()

    async def recall(self, query: str, limit: int = 5):
         """Recall memories - searches agent's session-scoped namespace"""
         if not self.session_token:
             await self.activate_session() # Activate if not already active

         response = await self.client.post(
             f"{self.memanto_url}/api/v2/agents/{self.agent_id}/recall",
             json={
                 "query": query,
                 "limit": limit
             },
             headers={
                 "X-Session-Token": self.session_token
             }
         )
         return response.json()["memories"]

    async def chat(self, message: str):
        """Handle a chat message with memory"""

        # 1. Recall relevant context from agent's memory
        context = await self.recall(message)

        # 2. Generate response using context
        # (Your LLM integration here)
        response = f"Based on what I remember: {context}"

        # 3. Remember this interaction
        await self.remember(
            f"User said: {message}. Agent replied: {response}",
            memory_type="event"
        )

        return response

# Usage
async def main():
    agent = MyAIAgent()
    await agent.activate_session() # Activate session once at the start

    # First conversation
    await agent.remember("Alice prefers email communication", "preference")
    print("✅ Stored preference")

    # Later conversation - agent remembers!
    memories = await agent.recall("How does Alice like to communicate?")
    print(f"✅ Recalled {len(memories)} relevant memories")
    # Agent will find: "Alice prefers email communication"

    # All memories are in ONE namespace, scoped to the agent and session:
    # memanto_agent_customer-support-bot (for the current session)

asyncio.run(main())
```

**Key improvements with simplified API:**
- **One namespace**: All agent memories in `memanto_agent_{agent_id}` (scoped to the session)
- **Automatic management**: No manual namespace or scope handling
- **Memory continuity**: Same agent + active session = persistent context
- **Simpler code**: Fewer parameters, less error-prone

---

## Step 5: Choose Your Agent Pattern

MEMANTO supports 6 different agent patterns. Choose the one that fits your use case:

| Pattern | Best For | Guide |
|---------|----------|-------|
| **Support Agent** | Customer service, helpdesk | [Pattern 1](AGENT_INTEGRATION_GUIDE.md#pattern-1-support-agent---customer-preference-memory) |
| **Project Agent** | Decision tracking, governance | [Pattern 2](AGENT_INTEGRATION_GUIDE.md#pattern-2-project-agent---decision-tracking) |
| **Tool-Heavy Agent** | Multi-step workflows, pipelines | [Pattern 3](AGENT_INTEGRATION_GUIDE.md#pattern-3-tool-heavy-agent---artifact-management) |
| **Collaborative Agent** | Multi-agent systems | [Pattern 4](AGENT_INTEGRATION_GUIDE.md#pattern-4-long-running-session-with-context-compression) |
| **Long-Running Session** | Extended conversations (weeks/months) | [Pattern 4](AGENT_INTEGRATION_GUIDE.md#pattern-4-long-running-session-with-context-compression) |
| **Multi-Scope Analytics** | Cross-user insights, recommendations | [Pattern 5](AGENT_INTEGRATION_GUIDE.md#pattern-5-multi-scope-agent---cross-user-intelligence) |

See [AGENT_PATTERNS_OVERVIEW.md](AGENT_PATTERNS_OVERVIEW.md) for a complete comparison.

---

## Next Steps

### For Developers Building Agents

1. **Read the Integration Guide**: [AGENT_INTEGRATION_GUIDE.md](AGENT_INTEGRATION_GUIDE.md)
   - Complete code examples for all 6 patterns
   - Best practices and error handling
   - Performance optimization tips

2. **Explore Advanced Features**:
   - [Batch Operations](ENHANCEMENTS_SUMMARY.md#1-batch-write-operations) - Store 100 memories in 1 API call
   - [Context Summarization](ENHANCEMENTS_SUMMARY.md#10-context-summarization-service) - Auto-compress old conversations
   - [Multi-Scope Search](ENHANCEMENTS_SUMMARY.md#3-multi-scope-search) - Query across users simultaneously

3. **Review API Documentation**:
   - Interactive: http://localhost:8000/docs
   - Architecture: [ARCHITECTURE_ONE_PAGER.md](ARCHITECTURE_ONE_PAGER.md)
   - All Enhancements: [ENHANCEMENTS_SUMMARY.md](ENHANCEMENTS_SUMMARY.md)

### For AI Agents (Runtime)

If you're an AI agent reading this:
 - See [AGENT_RUNTIME_GUIDE.md](AGENT_RUNTIME_GUIDE.md) for runtime API usage
 - API Reference: http://your-memanto-url/docs
 - Quick start: Use `/api/v2/agents/{id}/remember` and `/api/v2/agents/{id}/recall` endpoints

---

## Troubleshooting

### MEMANTO won't start

```bash
# Check if Moorcheh API key is valid
uv run python test_moorcheh.py

# Check logs
docker logs <container-id>

# Verify environment variables
echo $MOORCHEH_API_KEY
```

### Health check fails

```bash
# Test Moorcheh connectivity directly
curl -X GET "https://api.moorcheh.ai/v1/namespaces" \
  -H "Authorization: Bearer $MOORCHEH_API_KEY"

# Check MEMANTO logs for errors
docker logs memanto --tail 100
```

### Memory operations return errors

- **403 Forbidden**: Check your Moorcheh API key is valid
- **500 Internal Server Error**: Check MEMANTO logs
- **422 Validation Error**: Check request format matches API spec

---

## Production Checklist

Before deploying to production:

- [ ] Secure your Moorcheh API key (use secrets manager)
- [ ] Configure authentication for MEMANTO API (add auth middleware)
- [ ] Set up monitoring and alerting
- [ ] Enable structured logging
- [ ] Configure rate limiting
- [ ] Set up backup strategy
- [ ] Review security hardening guide
- [ ] Load test with expected traffic
- [ ] Set up CI/CD pipeline
- [ ] Document your agent's memory usage patterns

---

## Getting Help

- **Documentation**: Browse all .md files in this repository
- **API Reference**: http://localhost:8000/docs
- **Issues**: Report bugs on GitHub Issues
- **Moorcheh Support**: https://docs.moorcheh.ai
- **Contact**: Dr. Majid Fekri, CTO Moorcheh.ai

---

## What's Next?

Now that MEMANTO is running, you're ready to build memory-enabled AI agents!

**Recommended reading order:**
1. ✅ You are here: GETTING_STARTED.md
2. → [AGENT_INTEGRATION_GUIDE.md](AGENT_INTEGRATION_GUIDE.md) - Complete code examples
3. → [AGENT_PATTERNS_OVERVIEW.md](AGENT_PATTERNS_OVERVIEW.md) - Choose your pattern
4. → [ENHANCEMENTS_SUMMARY.md](ENHANCEMENTS_SUMMARY.md) - Advanced features
5. → [ARCHITECTURE_ONE_PAGER.md](ARCHITECTURE_ONE_PAGER.md) - System design

**Happy building!** 🚀
