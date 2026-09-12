# Demo Video Script — PR #1718: ChatGPT & Claude Migration Adapters

**Duration:** ~90 seconds  
**Tool:** `asciinema` or screen recorder

---

## Recording Steps

### 1. Intro (5s)
```bash
echo "=== Memanto: AI Conversation Migration ==="
echo "PR #1718 — ChatGPT & Claude → Memanto → OKF Bundle"
```

### 2. Run Demo Mode (15s)
```bash
cd examples/migrations/ai-conversations
python migrate.py --demo
```
**Show:** The full pipeline — load, map, export, validate with 100% recall.

### 3. Show the OKF Bundle (10s)
```bash
echo "=== Generated OKF Bundle ==="
tree okf_bundle/
echo ""
echo "=== Sample Memory File ==="
head -20 okf_bundle/memories/mem_0000_Building_a_REST_API_with_FastAPI.md
```

### 4. Run Validation (10s)
```bash
python validation/validate.py --source chatgpt --export ./sample_data/chatgpt_export.json
python validation/validate.py --validate-okf --okf-dir ./okf_bundle
```

### 5. ChatGPT Export → Memanto (20s)
```bash
# Show how a real ChatGPT export gets migrated
python migrate.py --source chatgpt --export ./sample_data/chatgpt_export.json --output ./demo_output
echo "=== Memories Created ==="
ls -la demo_output/
```

### 6. Claude Export → Memanto (15s)
```bash
python migrate.py --source claude --export ./sample_data/claude_export.json --output ./demo_output_claude
echo "=== Claude Memories ==="
ls -la demo_output_claude/
```

### 7. Show Key Features (15s)
```bash
echo "Key Features:"
echo "  - Tree-structured ChatGPT exports parsed correctly"
echo "  - Flat Claude exports handled"
echo "  - Memory type auto-classification deferred to Memanto"
echo "  - Provenance metadata preserved"
echo "  - OKF bundle: portable, human-readable"
echo "  - 100% recall parity on demo data"
```

---

## Recording Command (asciinema)
```bash
asciinema rec -c "bash run_demo.sh" demo_v1718.cast
```

## After Recording
Upload to Loom or YouTube and add the link to the PR description.
