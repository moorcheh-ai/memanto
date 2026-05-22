# Memanto + LangGraph Integration: Customer Support Agent with Permanent Memory

A complete example demonstrating how Memanto provides **cross-session long-term memory** for LangGraph agents. This customer support agent remembers user preferences, past issues, and resolutions across completely separate conversations.

## 🎥 Demo Video

[![Demo Video](https://img.youtube.com/vi/placeholder/0.jpg)](https://www.youtube.com/watch?v=placeholder)

> 🔗 **Full demo video**: [Watch on YouTube](https://www.youtube.com/watch?v=placeholder) (30-second walkthrough of cross-session recall)

## ✨ What This Demonstrates

### Cross-Session Recall
The agent remembers information from "yesterday" that isn't in the current thread's state:

- **Session 1 (Monday)**: User mentions they're allergic to peanuts and had a billing issue
- **Session 2 (Tuesday, new thread)**: Agent proactively asks about the billing resolution and avoids peanut-related recommendations
- **No state persistence**: This works across separate Python processes, not just within the same runtime

## 🏗️ Architecture

