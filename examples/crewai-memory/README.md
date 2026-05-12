# CrewAI + Memanto Example

This directory contains a real-world example of CrewAI agents using **Memanto** as their shared, persistent memory layer. Two agents collaborate through a semantic memory database that survives across sessions, agents, and runs.

> **Note**: The core integration tools used in this example are published to PyPI as `memanto-crewai`. For deep documentation on the architecture, setup instructions, and API details of the integration itself, please read the [memanto-crewai package README](../../integrations/crewai/README.md).

## Architecture

![CrewAI + Memanto: Persistent Multi-Agent Memory](https://github.com/moorcheh-ai/memanto/raw/main/assets/crewai-architecture.png)

## What This Demonstrates

- **Cross-agent memory sharing**: A Research Agent stores findings that a Writer Agent retrieves
- **Cross-session persistence**: Run the researcher today, run the writer tomorrow -- memories persist
- **Typed semantic memory**: 13 memory types (fact, observation, decision, etc.) with confidence scoring
- **Contradictory memory handling**: Detect and resolve conflicting facts (bonus)

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenRouter API key](https://openrouter.ai/keys) (for CrewAI's LLM — free tier available)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENROUTER_API_KEY
```

## Step-by-Step Demo (Proves Persistence)

This is the recommended flow for your terminal recording:

```bash
# Step 1: Research Agent stores findings in Memanto
python run_research.py

# Step 2: Writer Agent retrieves those memories in a NEW session
# (This proves memories persist across sessions!)
python run_writer.py

# Step 3 (Bonus): Demonstrate contradictory memory handling
python run_contradiction.py
```

## File Structure

```text
examples/crewai-memory/
├── README.md              # This file
├── requirements.txt       # Python dependencies (includes memanto-crewai)
├── .env.example           # API key template
├── agents.py              # Research Agent + Writer Agent definitions
├── tasks.py               # Task definitions
├── crew.py                # Crew orchestration factories
├── run_research.py        # Run 1: Research Agent stores findings
├── run_writer.py          # Run 2: Writer Agent recalls (proves persistence)
├── run_full_pipeline.py   # Full pipeline in one run
└── run_contradiction.py   # Bonus: contradictory memory handling
```

## Bonus: Cursor Integration

After running the CrewAI pipeline, you can access the same memories from Cursor:

```bash
memanto connect cursor --global
```

Open any project in Cursor and ask it to recall your research findings -- it accesses the same Memanto memory namespace used by the CrewAI agents.

**Example Cursor prompt after running the CrewAI pipeline:**
> "Use memanto recall to find what the research team stored about AI agent market size"
