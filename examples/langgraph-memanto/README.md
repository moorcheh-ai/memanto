## LangGraph + Memanto: Research Mentor with Persistent Memory

A LangGraph agent that uses **Memanto** as its long-term memory layer, enabling seamless cross-session recall. The agent remembers your research context, experimental results, preferences, and deadlines — even across completely independent sessions.

### Architecture

```
User Input
    │
    ▼
┌─────────┐     ┌────────────┐     ┌──────────┐     ┌─────────┐     ┌───────┐
│  intake  │ ──▸ │   recall   │ ──▸ │ generate │ ──▸ │ extract │ ──▸ │ store │
│          │     │            │     │          │     │         │     │       │
│ append   │     │  Memanto   │     │ LLM with │     │ LLM ──▸ │     │ write │
│ to chat  │     │  semantic  │     │ memory   │     │ JSON of │     │ to    │
│ history  │     │  search    │     │ context  │     │ new     │     │Memanto│
└─────────┘     └────────────┘     └──────────┘     │ facts   │     └───────┘
                     ▲                                └─────────┘        │
                     │                                                   │
                     └───────────── Memanto Server ──────────────────────┘
                                  (persistent store)
```

**Key design decision**: Memory context comes from Memanto at runtime, never from LangGraph's state checkpoint. This is what makes cross-session recall work — a brand new graph instance can access all historical memories.

### Quick Start

```bash
# 1. Get a Moorcheh API key (free) from https://console.moorcheh.ai
export MOORCHEH_API_KEY=your-key-here
export OPENAI_API_KEY=sk-your-key-here

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the Memanto server
memanto serve

# 4. Run the cross-session demo
python demo.py

# 5. Or run interactively
python main.py
```

### Cross-Session Demo

The demo (`demo.py`) runs two fully independent sessions:

**Session 1 ("Yesterday")** — The user discusses their LLM inference optimization research, shares experimental results, tool preferences, and deadlines. Memanto silently stores these as typed memories.

**Session 2 ("Today")** — A completely new `ResearchMentor` instance with zero shared state. The user asks "What was I working on?" and "What results did I get?" — answered entirely from Memanto's persistent memory.

<!-- TODO: Record demo.py and add GIF link below -->
<!-- ![Demo GIF](demo.gif) -->

### Programmatic Usage

```python
import asyncio
from main import ResearchMentor

async def main():
    async with ResearchMentor(agent_name="my-agent") as mentor:
        # Session 1
        await mentor.chat("I'm building a recommendation engine using collaborative filtering.")
        await mentor.chat("User engagement improved 23% in A/B testing.")

    # ... later, or in a completely different process ...

    async with ResearchMentor(agent_name="my-agent") as mentor:
        # Session 2 — memories from Session 1 are automatically recalled
        response = await mentor.chat("What were my A/B test results?")
        print(response)  # References the 23% improvement

asyncio.run(main())
```

### Memory Types

The agent stores memories with Memanto's typed schema:

| Type | When Used | Example |
|------|-----------|---------|
| `fact` | Concrete information | "User's model is Llama-3-8B" |
| `preference` | User's tool/style choices | "Prefers PyTorch over TensorFlow" |
| `goal` | Objectives and targets | "Aiming for sub-10ms latency" |
| `decision` | Choices made | "Chose AWQ over GPTQ quantization" |
| `event` | Things that happened | "Ran benchmark on RTX 4090" |
| `commitment` | Deadlines, promises | "Paper deadline is March 15th" |
| `learning` | Insights discovered | "4-bit quantization gives best speed/quality tradeoff" |

### Files

| File | Description |
|------|-------------|
| `main.py` | LangGraph workflow + `ResearchMentor` wrapper + interactive CLI |
| `demo.py` | Cross-session demo proving persistent recall |
| `memanto_client.py` | Async HTTP client for Memanto v2 API |
| `requirements.txt` | Python dependencies |

### How It Works

1. **`intake`** — Appends the user's message to the conversation history
2. **`recall`** — Queries Memanto for semantically similar memories from *all* prior sessions
3. **`generate`** — Calls the LLM with recalled memories injected into the system prompt
4. **`extract`** — Uses a second LLM call to identify new facts, preferences, and decisions
5. **`store`** — Writes extracted memories to Memanto with types, confidence scores, and tags

The separation between *generate* and *extract* ensures the user gets a natural response while new knowledge is precisely catalogued for future recall.
