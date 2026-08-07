# ChatGPT Data Export Migration Showcase

This directory showcases how to migrate your ChatGPT conversational history into Memanto memories, and optionally export them to the Open Knowledge Format (OKF) for true data portability.

## Overview

The Memanto CLI natively supports parsing ChatGPT's `conversations.json` data export file. It walks through your chat history, extracting messages and formatting them as rich Memanto memories with the appropriate metadata (timestamps, conversation IDs, roles, etc).

Because it uses Memanto's core migration framework, you get a clean dry-run preview, batch writing, and the ability to seamlessly convert to OKF.

## How to use

1. **Request your data from ChatGPT**
   - In ChatGPT, go to Settings -> Data controls -> Export data.
   - You will receive a ZIP file containing `conversations.json`.

2. **Preview the migration**
   Run a dry-run to see exactly how your conversations map to Memanto's schema:
   ```bash
   memanto migrate chatgpt --file ./conversations.json --dry-run
   ```

3. **Perform the migration**
   Import the data into your active Memanto agent:
   ```bash
   memanto migrate chatgpt --file ./conversations.json
   ```

4. **Export to OKF (Optional)**
   Now that your memories are in Memanto, you can export your agent to a portable OKF bundle:
   ```bash
   memanto okf export --agent <your-agent-id> --out ./my-okf-bundle
   ```

## Try the sample

You can test the flow right away using the provided `sample_conversations.json`:

```bash
memanto migrate chatgpt --file examples/migrations/chatgpt-export/sample_conversations.json --dry-run
```
