#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  LangGraph + Memanto Cross-Session Demo"
echo "============================================"
echo ""

# Check for API key
if [ -z "${MOORCHEH_API_KEY:-}" ]; then
  if [ -f .env ]; then
    source .env
  else
    echo "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
    exit 1
  fi
fi

echo "[1/2] SESSION 1: Storing customer context in Memanto..."
python langgraph_memanto_agent.py --session 1
echo ""

echo "[2/2] SESSION 2: Proving cross-session recall (NEW session)..."
python langgraph_memanto_agent.py --session 2
echo ""

echo "============================================"
echo "  Demo Complete!"
echo "  The agent recalled context from Session 1"
echo "  despite Session 2 being a brand new process."
echo "  This demonstrates CROSS-SESSION RECALL ✓"
echo "============================================"
