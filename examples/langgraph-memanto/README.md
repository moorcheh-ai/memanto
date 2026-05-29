# Memanto + LangGraph Integration: Customer Support Agent with Permanent Memory

This example demonstrates how to use **Memanto** as the long-term memory layer for a **LangGraph** agent. The agent is a customer support assistant that remembers facts about users across sessions—even when the conversation thread is completely new.

## 🎥 Demo

![Customer Support Agent Demo](https://i.imgur.com/placeholder.gif)

> **Video Demo:** [Watch on YouTube](https://www.youtube.com/watch?v=placeholder) (30 seconds)

## What This Example Shows

- **Cross-Session Recall**: The agent remembers user preferences and facts from "yesterday" that aren't in the current thread's state.
- **Typed Memory**: Uses Memanto's semantic memory to store user preferences, episodic memory for conversation history, and procedural memory for support workflows.
- **LangGraph Integration**: Clean integration with LangGraph's state management and tool calling.

## Architecture

