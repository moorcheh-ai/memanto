# Two-minute live demo runbook

This is the recording checklist for the mandatory bounty video. Record the
terminal and editor; do not substitute slides for the live commands.

1. Show the committed Claude Code source:

   ```bash
   find examples/migrations/claude-code/sample_data/.claude -type f
   sed -n '1,80p' examples/migrations/claude-code/sample_data/.claude/history.jsonl
   ```

2. Run the reproducible migration:

   ```bash
   ./examples/migrations/claude-code/run_sample.sh
   ```

3. Pause on the evidence:
   - 5 source records → 3 mapped memories;
   - `context`, `fact`, and `preference`;
   - 0 skipped records;
   - 5/5 source recall and 5/5 OKF recall;
   - 3 mapped memories and 0 skips in Memanto's own dry-run.

4. Open one generated memory:

   ```bash
   sed -n '1,160p' \
     examples/migrations/claude-code/sample_output/okf/memories/fact/auto-planmaxxer-project-context.md
   ```

5. Close on the ownership story: the memory began as Claude Code-local state
   and is now readable, git-friendly OKF accepted by Memanto's shipped
   importer. For a live keyed demo, follow with:

   ```bash
   uv run memanto migrate okf \
     examples/migrations/claude-code/sample_output/okf \
     --agent claude-code-demo
   uv run memanto memory export --agent claude-code-demo --okf \
     --output ./owned-again-okf
   ```

The public upload and social post must link to the pull request and tag the
official Moorcheh account as required by bounty issue #1609.
