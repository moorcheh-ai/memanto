# LangGraph + Memanto Support Agent

This example demonstrates how to use Memanto as an external, permanent memory store for a LangGraph workflow. It solves the problem of cross-session amnesia in standard LangGraph thread states by pulling in a `user_profile` at the start of the graph execution.

## Demo
(GIF Link goes here)

## How it works
1. **Recall Node**: Queries Memanto for the user's historical profile before processing the chat.
2. **Chat Node**: Uses the LLM to generate a response, conditioned on the permanent memory.
3. **Store Node**: Extracts new preferences and persists them back to Memanto for future sessions.
