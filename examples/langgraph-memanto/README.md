# LangGraph + Memanto Integration

This example demonstrates how to give a LangGraph agent a "permanent brain" using Memanto as a long-term memory layer, enabling recall across disjointed sessions.

## Features
- **Cross-Session Recall**: Agent remembers facts stored in previous execution cycles.
- **Tool-Based Memory**: Memory operations are bound as LangChain tools for autonomous usage.
- **State Persistence**: Uses Memanto's SDK to decouple long-term memories from the short-term LangGraph state.

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your environment variables:
   ```bash
   export OPENAI_API_KEY='your-key'
   export MEMANTO_API_KEY='your-key'
   export MEMANTO_BASE_URL='your-url'
   ```

## Running the Demo
To start an interactive session:
```bash
python main.py
```

To run the automated cross-session persistence test:
```bash
python full_pipeline_demo.py
```

## Demo
![Agent Demo](https://github.com/moorcheh-ai/memanto/assets/memanto-logo.png)
*(Replace with actual GIF/Video link in PR)*
