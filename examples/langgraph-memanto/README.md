# LangGraph + Memanto Integration

This example demonstrates how to use Memanto as a long-term memory layer for a LangGraph agent, enabling cross-session recall.

## Features
- **Cross-Session Recall**: The agent remembers user preferences and facts across different session IDs.
- **LangGraph Workflow**: Implements a retrieve-reason-store loop.
- **Memanto Integration**: Uses Memanto for storing and retrieving memories outside of the standard LangGraph state.

## Setup
1. Start the Memanto server.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your OpenAI API Key:
   ```bash
   export OPENAI_API_KEY='your-api-key'
   ```
4. Run the example:
   ```bash
   python main.py
   ```

## Workflow
1. **Retrieve**: Searches Memanto for memories relevant to the current user and query.
2. **Model**: The LLM generates a response using the retrieved memories.
3. **Store**: New information is stored back into Memanto for future sessions.

## Demo
![Demo GIF](https://via.placeholder.com/300x200?text=Agent+Demo+GIF)
