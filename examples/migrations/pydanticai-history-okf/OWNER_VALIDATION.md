# Owner-run live validation

The committed sample proves source generation, conversion, Memanto mapping,
exact reconstruction, privacy scanning, and credential-free recall parity. The
bounty owner should add the following evidence only after personally running
the credentialed operations against an account they control.

## Before the run

1. Inspect `sample/source/history.json` and confirm it contains only public demo
   data.
2. Inspect `sample/okf/migration-manifest.json` and confirm `lossless: true`, 20
   source messages, 20 mapped memories, and zero skipped messages.
3. Configure Memanto using its documented login or API-key flow. Never put a
   key in this repository, a shell transcript, a screen recording, or a PR.
4. Create or choose a dedicated test agent so the imported memories cannot be
   confused with unrelated account data.

## Import and export back

Replace `YOUR_AGENT_ID` with the dedicated agent you verified:

```bash
memanto migrate okf ./sample/okf --agent YOUR_AGENT_ID
memanto memory export --okf --agent YOUR_AGENT_ID \
  --output ./live-evidence/exported-okf
```

Keep the complete terminal result. The import must report 20 mapped memories,
zero skipped records, 20 imported records, and zero failures before those facts
can be stated publicly. Inspect the exported OKF rather than relying on an exit
code alone.

## Live recall matrix

Run the six questions from `sample/golden_qa.json` against the dedicated agent:

```bash
memanto agent activate YOUR_AGENT_ID
memanto recall "What PydanticAI source package and version did the project record?"
memanto recall "Which merge-ready output folder replaced the earlier folder name?"
memanto recall "What are the bounty deadline and prize?"
memanto recall "What did I commit to include for the migration submission?"
memanto recall "When is it acceptable to claim a live Moorcheh import?"
memanto recall "What privacy behavior must generated bundles use?"
```

For each query, compare the returned content with the corresponding
`expected_substrings` entry. Record the result as pass only when every expected
substring is present in the retrieved context. Do not rewrite a failed result;
keep it and improve the migration or query evidence.

## Evidence to attach

- Memanto version and Python version.
- Import summary and generated run-directory path.
- Export-back folder manifest and memory count.
- All six live recall commands and their unedited results.
- Start/end timestamps and exit codes.
- A screen recording showing the commands and inspectable Markdown.
- Public video/social URLs required by the bounty issue.
- Accurate assistance and authorship disclosure required by the repository and
  bounty platforms.

Do not claim a live import, a live recall score, public reach, or social metrics
from the committed credential-free sample. Those are separate owner-run facts.
