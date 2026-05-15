
# LangGraph + Memanto: Cross-Session Memory Example

## Architecture

LangGraph workflow with Memanto as the external long-term memory layer.

## What This Demonstrates

- **Cross-session recall**: Agent remembers info from "yesterday" that isn't in current thread state
- **Fitness Coach** demo: custom workout plans, dietary preferences, injury tracking, progress notes
- **Blog Writer** demo: audience profiles, tone preferences, past article facts, overused phrases
- **Travel Planner** demo: visa requirements, hotel preferences, budget rules, past itineraries
- **Real Memanto adapter** (`SdkClient`) and **local JSON fallback** (no API key needed)

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month) - optional for local mode
- An [OpenAI API key](https://platform.openai.com/api-keys) (for LangChain LLM)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env, add OPENAI_API_KEY (and MOORCHEH_API_KEY for real Memanto mode)
```

## Run the Demos

```bash
# Local mode (no API keys besides OpenAI):
python run_demo.py

# Real Memanto mode (requires MOORCHEH_API_KEY):
MEMANTO_MODE=real python run_demo.py
```

## File Structure

```text
examples/langgraph-memanto/
├── README.md
├── requirements.txt
├── .env.example
├── langgraph_memanto.py    # Core: MemoryClient protocol, adapters, LangGraph workflow
├── run_demo.py             # 4 demos: fitness coach, blog writer, travel planner, per-job
└── demo.gif               # 30-second demo GIF
```

## Demo: Fitness Coach

```
Session 1: Coach stores workout plan, dietary preferences, injury history
Session 2 (fresh state): Coach recalls everything, gives personalized advice
```

## Demo: Blog Writer

```
Session 1: Writer stores audience profiles, tone preferences, article drafts
Session 2 (fresh state): Writer recalls past context, avoids overused phrases, keeps tone consistent
```

## Demo: Travel Planner

```
Session 1: Planner stores visa info, hotel preferences, budget rules, itineraries
Session 2 (fresh state): Planner recalls past trips, gives destination-specific tips
```

