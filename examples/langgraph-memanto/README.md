# LangGraph + Memanto: Give Your Graph a Permanent Brain

This example demonstrates how to integrate **Memanto** into a **LangGraph** workflow to provide long-term, cross-session persistence.

Unlike standard LangGraph state (which is transient or scoped to a single thread), Memanto allows your agents to remember facts, preferences, and decisions across days, weeks, or entirely different graph instances.

## What This Demonstrates

- **Cross-Session Recall**: The agent remembers the user's name and preferences across completely independent runs.
- **Semantic Memory**: Using `memanto_recall` to find relevant information based on natural language queries.
- **Memory Storage**: Using `memanto_remember` to save new insights during the conversation.

## Architecture

Memanto acts as an external toolset that the LangGraph agent can call. When the agent uses `memanto_remember`, the information is stored in Memanto's persistent semantic database. When the agent needs information from a previous session, it uses `memanto_recall` or `memanto_answer` to retrieve it.

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys)
- An OpenAI API key (or any other provider supported by LangChain)

## Setup

