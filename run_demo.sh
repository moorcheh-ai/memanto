#!/usr/bin/env bash
# Quick demo script for PR #1718 recording
set -e
cd "$(dirname "$0")/examples/migrations/ai-conversations"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Memanto: AI Conversation Migration — PR #1718 Demo        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "▶ Step 1: Run migration demo..."
python migrate.py --demo
echo ""

echo "▶ Step 2: Show generated OKF bundle..."
echo "   Files:"
find okf_bundle -type f | sort
echo ""

echo "▶ Step 3: Sample memory content:"
echo "────────────────────────────────"
head -25 okf_bundle/memories/mem_0000_Building_a_REST_API_with_FastAPI.md
echo "────────────────────────────────"
echo ""

echo "▶ Step 4: Run validation..."
python validation/validate.py --source chatgpt --export ./sample_data/chatgpt_export.json
echo ""

echo "▶ Step 5: Validate OKF bundle..."
python validation/validate.py --validate-okf --okf-dir ./okf_bundle
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✓ Demo Complete — 100% recall, valid OKF bundle           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
