---
type: Context Document
title: okf-fidelity-loop_2026-09-01_sess_f5d67e552130_summary
---

# Session Summary for okf-fidelity-loop
**Session ID:** `sess_f5d67e552130`

---

### [2026-09-01 21:25:52] [FACT] Four shipped migration mappers
- **Memory ID**: `1ffa2d67-23e5-4304-b085-afef16392434`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `migrate`, `okf`
- **Content**:
> Memanto's migrate CLI ships four mappers: mem0, letta, supermemory and okf. Anything else has to reach the CLI as a provider-shaped export JSON or as an OKF bundle.

---

### [2026-09-01 21:25:52] [DECISION] Langfuse stays out of MAPPERS
- **Memory ID**: `406bf96b-99b7-494c-b79b-996169d9a87c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `migrate`, `langfuse`
- **Content**:
> Langfuse is deliberately absent from the MAPPERS registry: its rows are observability events, not memories, so one incident collapses into a single grouped payload instead of mapping row-for-row.

---

### [2026-09-01 21:25:52] [FACT] Only memories/ is importable
- **Memory ID**: `d5ef1f6c-544f-4b19-b0df-c9d3fd55a30e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `import`
- **Content**:
> An OKF bundle nests importable memories under memories/. The sibling daily-summaries/, sessions/ and metrics/ folders are export-only context and are skipped on import, so re-importing a bundle never re-ingests its own logs.

---

### [2026-09-01 21:25:52] [FACT] x_memanto carries the round trip
- **Memory ID**: `bc3d6dc3-52bf-47e3-bf34-6f5254a784b3`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `roundtrip`
- **Content**:
> Memanto-only fields (id, confidence, provenance, source, status and the temporal metadata) ride in a namespaced x_memanto frontmatter block. OKF consumers ignore unknown keys, so Memanto -> OKF -> Memanto keeps them.

---

### [2026-09-01 21:25:52] [INSTRUCTION] The import flag is --agent
- **Memory ID**: `686c3b97-cd07-4a8f-9848-fde7f6deaa0a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Import an OKF bundle with `memanto migrate okf <path> --agent <id>`. The flag is --agent (short -a), not --agent-id; four of the open bounty PRs document a flag that does not exist.

---

### [2026-09-01 21:25:52] [ERROR] Bundle output is sandboxed to ~/.memanto
- **Memory ID**: `78b38a81-3ca8-47d6-8c73-4133e636c764`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `export`
- **Content**:
> write_okf_bundle refuses any output_dir outside the agent data directory. To write a bundle somewhere else, construct OkfExportService with a custom exports_dir; its parent bounds what the service will accept.

---

### [2026-09-01 21:25:52] [PREFERENCE] auto split at 50 memories
- **Memory ID**: `2f155c2a-e4a4-4e5b-9568-d75c99d269bb`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `layout`
- **Content**:
> OKF layout defaults to split=auto: a type with 50 or fewer memories gets one file per memory, a larger type collapses into a single stacked file so high-volume agents do not produce thousands of files.

---

### [2026-09-01 21:25:52] [ARTIFACT] okf-entry separates stacked documents
- **Memory ID**: `1910baa3-1f88-470d-a7b7-e86980b07920`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `format`
- **Content**:
> Stacked OKF files hold several documents separated by the <!-- okf-entry --> sentinel, so a body containing its own --- rule cannot be mistaken for a document boundary.

---

### [2026-09-01 21:25:52] [LEARNING] Round trips must be idempotent
- **Memory ID**: `fe8a712a-de71-448a-9973-c335071d1244`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `roundtrip`, `fidelity`
- **Content**:
> Repeated OKF round trips used to stack one [Supporting data] footer per cycle, because _attach_footer appended unconditionally to content that already carried the previous pass's footer. Stripping it first makes the loop converge.

---

### [2026-09-01 21:25:52] [OBSERVATION] Unmapped OKF types defer to auto-classification
- **Memory ID**: `cb9f6de0-7e3e-48ff-bbdf-a2b065489d3e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `okf`, `types`
- **Content**:
> map_okf leaves type=None when OKF's free-form type has no Memanto slot, deferring to server-side auto-classification, and records the original OKF type in the supporting-data footer instead.

---

### [2026-09-01 21:25:52] [CONTEXT] ruff covers examples/, mypy does not
- **Memory ID**: `ed3db4ec-2f06-4423-b0f2-359903e8cc5b`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `ci`, `lint`
- **Content**:
> CI runs ruff check and ruff format over the whole repository; only legacy_archive is excluded. mypy skips examples/, but ruff does not, so an example with an unused import fails the build.

---

### [2026-09-01 21:25:52] [RELATIONSHIP] How the OKF import path fits together
- **Memory ID**: `477f8272-3f04-4efb-bc40-7fad42c033aa`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `validated`
- **Tags**: `migrate`, `architecture`
- **Content**:
> load_okf_bundle parses a bundle into entries, map_okf turns those entries into batch-remember rows, and run_migration imports them in batches of 100. A new adapter only has to produce the bundle.

---

### [2026-09-01 21:25:52] [GOAL] Idempotent portability
- **Memory ID**: `a72e0b35-0768-4fd1-bd0b-af0d82440542`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `explicit_statement`
- **Tags**: `okf`, `fidelity`
- **Content**:
> Prove the freedom loop is idempotent: carrying an agent's memory out to OKF and back must be a no-op, however many times you do it.

---

### [2026-09-01 21:25:52] [COMMITMENT] Harness stays key-free
- **Memory ID**: `da738774-50e0-4821-97f5-19b0adee585a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `explicit_statement`
- **Tags**: `examples`, `reproducibility`
- **Content**:
> Keep this example offline and key-free after the fixture exists, so anyone can reproduce the fidelity result without a Moorcheh account.

---

### [2026-09-01 21:25:52] [EVENT] Reviewed 65 bounty PRs
- **Memory ID**: `519c953d-dfeb-4b9f-8f01-a4e423300d3f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-review`
- **Provenance**: `observed`
- **Tags**: `bounty`, `review`
- **Content**:
> Reviewed all 65 open PRs on bounty #1609 before adding this example. Every one of them tested a single export/import hop; none tested a second one, which is where the footer drift appears.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent create
- **Memory ID**: `f5384248-8331-4f0a-9c3b-1182d30d40bc`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent create` to create a new agent and activate it immediately.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent list
- **Memory ID**: `a7096872-810f-480e-9140-797983e4a840`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent list` to list all agents.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent activate
- **Memory ID**: `71d927dc-a05e-44ae-a1f3-35c89aac1c1f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent activate` to activate an agent and start its active session.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent deactivate
- **Memory ID**: `6068cdf3-f8be-43d4-8d1d-c2be13d7726c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent deactivate` to deactivate the currently active agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent delete
- **Memory ID**: `2e9d9e98-d3dc-42d8-8614-be65cacdfe27`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent delete` to delete an agent and optionally purge its cloud memories.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto agent bootstrap
- **Memory ID**: `d169d110-3228-40e3-8011-6036f041409a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `agent`
- **Content**:
> Run `memanto agent bootstrap` to generate an intelligence snapshot of an agent's memory.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto config show
- **Memory ID**: `139c1397-f3f6-48bf-a77b-cd5c22de9bfe`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `config`
- **Content**:
> Run `memanto config show` to display current configuration.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto config backend
- **Memory ID**: `eaa4b808-761b-4c42-97f8-264c70d390fb`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `config`
- **Content**:
> Run `memanto config backend` to show or switch the active Moorcheh backend.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect claude-code
- **Memory ID**: `4feac30b-c4e3-4801-ab66-826b1c52747f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect claude-code` to connect MEMANTO to Claude Code.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect codex
- **Memory ID**: `f11380d0-ba2f-4d3d-b55e-ddd6161f6094`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect codex` to connect MEMANTO to OpenAI Codex CLI.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect pi
- **Memory ID**: `f94bee0d-8541-4986-b80f-709286131b0f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect pi` to connect MEMANTO to Pi (coding agent).

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect cursor
- **Memory ID**: `65903d33-b9f4-4e2f-aaed-67c60eaa55f3`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect cursor` to connect MEMANTO to Cursor IDE.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect windsurf
- **Memory ID**: `57474d31-67e1-4fbb-81d9-2a44b5462669`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect windsurf` to connect MEMANTO to Windsurf IDE.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect antigravity
- **Memory ID**: `adca907d-2114-4c5d-966e-7c8cfe3a001a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect antigravity` to connect MEMANTO to Google Antigravity.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect gemini-cli
- **Memory ID**: `e0c134f8-4560-4bf6-89d8-7a68002e8236`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect gemini-cli` to connect MEMANTO to Google Gemini CLI.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect cline
- **Memory ID**: `a36001f5-c194-4289-986d-c3d606f1484b`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect cline` to connect MEMANTO to Cline VS Code extension.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect continue
- **Memory ID**: `e9c2f5c2-a02c-4de1-90f4-600cb464bfda`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect continue` to connect MEMANTO to Continue.dev.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect opencode
- **Memory ID**: `b1770b40-34ac-4071-9d5d-c11c90709c86`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect opencode` to connect MEMANTO to OpenCode CLI.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect goose
- **Memory ID**: `bea666f0-0555-4b81-81e7-ea93091026e4`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect goose` to connect MEMANTO to Goose AI agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect roo
- **Memory ID**: `7a42d6e9-420c-48ce-8d04-26cabbfc46ca`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect roo` to connect MEMANTO to Roo Code.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect github-copilot
- **Memory ID**: `98e146cd-ff57-44f5-b362-18fa7b6e7e8e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect github-copilot` to connect MEMANTO to GitHub Copilot.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect augment
- **Memory ID**: `b2651c0f-66c1-4821-b96f-9aa0f38292ff`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect augment` to connect MEMANTO to Augment Code.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect list
- **Memory ID**: `97e73c22-0305-47e6-8823-fb0fa1147b6a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect list` to list all supported agents and their MEMANTO installation status.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect remove
- **Memory ID**: `29ff743f-a211-487f-a272-40b5ec9cf941`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect remove` to remove MEMANTO integration from an agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto connect multi
- **Memory ID**: `c1337829-ab46-470b-86dd-5ff6027dea59`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `connect`
- **Content**:
> Run `memanto connect multi` to interactive setup — select multiple agents to connect.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto status
- **Memory ID**: `740bb0f6-125f-47e4-9804-4e8320e333cc`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto status` to show comprehensive MEMANTO scenario dashboard.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto serve
- **Memory ID**: `8145a9ce-dfa6-4512-9b82-6fb6402083d9`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto serve` to start MEMANTO server.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto ui
- **Memory ID**: `e093f639-e047-435c-847d-da0881d8a258`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto ui` to start MEMANTO server and open the Web UI Dashboard.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto remember
- **Memory ID**: `fafb83cd-f876-4323-8c01-ba319115ac95`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto remember` to store a new memory for the active agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto edit
- **Memory ID**: `75bf7eb4-032f-4f3b-9bbc-755f518a74bd`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto edit` to update fields on an existing memory for the active agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto memory expire
- **Memory ID**: `1426826e-3760-4750-9eae-5ea9f5415296`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `memory`
- **Content**:
> Run `memanto memory expire` to expire a memory without deleting it.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto memory restore
- **Memory ID**: `7d3b9b7a-3b15-4366-8059-7d3757438a5f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `memory`
- **Content**:
> Run `memanto memory restore` to return an expired memory to the active state.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto forget
- **Memory ID**: `b11bcb6a-dbde-48f5-94e6-058b564cbda7`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto forget` to permanently delete a single memory from the active agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto upload
- **Memory ID**: `0a3d7679-8089-42d1-9455-badef92c717e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto upload` to upload a file to the active agent's memory namespace.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto recall
- **Memory ID**: `022717e6-1431-4a18-92f7-015d4b4b3216`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto recall` to search and retrieve memories for the active agent with temporal query support.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto answer
- **Memory ID**: `3eb919b6-256c-40d5-91b6-e3a9dc9ea41b`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto answer` to answer a question using RAG (Retrieval-Augmented Generation).

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto daily_summary
- **Memory ID**: `22f36600-0292-495a-a002-60be8fd6a55b`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto daily_summary` to generate a daily AI summary from session memories.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto detect-conflicts
- **Memory ID**: `237279bb-c373-422d-b1b1-6c8b92b5b2f0`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto detect-conflicts` to generate the conflict report for an agent/date.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto conflicts
- **Memory ID**: `51ce9fa9-dc10-4aae-9a3e-1a1ae9488edc`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `core`
- **Content**:
> Run `memanto conflicts` to interactively resolve memory conflicts for an agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto memory export
- **Memory ID**: `dc41e2a4-3db0-4d59-ab79-f27bfbe7ba57`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `memory`
- **Content**:
> Run `memanto memory export` to export all memories into a structured memory.md file.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto memory sync
- **Memory ID**: `dcb052a6-c4d7-40d0-9f4a-2ead57323d2f`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `memory`
- **Content**:
> Run `memanto memory sync` to sync agent memories to a project directory's MEMORY.md.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto migrate mem0
- **Memory ID**: `ad937025-ede3-40cf-99b7-c979e9f240de`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Run `memanto migrate mem0` to migrate a Mem0 account into the active (or selected) Memanto agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto migrate letta
- **Memory ID**: `d217a1bb-8169-4e71-86b0-485dec337b07`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Run `memanto migrate letta` to migrate Letta archival passages into the active (or selected) Memanto agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto migrate okf
- **Memory ID**: `c0c6df44-14ba-4b2e-aaca-5c85c0fc0041`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Run `memanto migrate okf` to import an OKF (Open Knowledge Format) bundle into the active (or selected) agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto migrate supermemory
- **Memory ID**: `0d9b769a-8cf0-439c-b920-d46fa7a572d2`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Run `memanto migrate supermemory` to migrate a Supermemory account into the active (or selected) Memanto agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto migrate langfuse
- **Memory ID**: `254adc5f-3c54-497a-b3ae-a16580cff46c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `migrate`
- **Content**:
> Run `memanto migrate langfuse` to sync Langfuse observability signal into the active (or selected) agent.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto policy show
- **Memory ID**: `693c8496-44ff-4626-a4e6-fed3c948ac99`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `policy`
- **Content**:
> Run `memanto policy show` to show the agent's current expiry policy.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto policy list-preset
- **Memory ID**: `cbd1e644-f27c-4445-8f0d-0b6645cf8a86`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `policy`
- **Content**:
> Run `memanto policy list-preset` to list the predefined policy bundles.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto policy apply-preset
- **Memory ID**: `2d5a5247-5f78-46d9-9ffa-62d8ccace900`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `policy`
- **Content**:
> Run `memanto policy apply-preset` to adopt a predefined policy bundle, replacing the current policy.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto policy apply
- **Memory ID**: `9af23a91-b435-4fde-ba43-ca4d2a858247`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `policy`
- **Content**:
> Run `memanto policy apply` to sweep the agent's memories and expire everything the policy matches.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto policy purge
- **Memory ID**: `bcd1774f-1bf6-4e45-b967-eeaab7e08906`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `policy`
- **Content**:
> Run `memanto policy purge` to permanently delete memories expired longer than the purge window.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto schedule enable
- **Memory ID**: `b24f0237-3a55-4213-83e5-a6b1a8966366`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `schedule`
- **Content**:
> Run `memanto schedule enable` to enable the nightly daily-summary + conflict-detection + expiry-sweep job.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto schedule disable
- **Memory ID**: `586fa5e4-3008-4cbb-adab-76f4d527ad39`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `schedule`
- **Content**:
> Run `memanto schedule disable` to disable the nightly daily-summary + conflict-detection + expiry-sweep job.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto schedule _run
- **Memory ID**: `30942229-bd31-4ea3-b277-f49f78869053`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `schedule`
- **Content**:
> Run `memanto schedule _run` to internal entrypoint invoked by the OS scheduler. Runs daily-summary, then detect-conflicts, then the expiry sweep in one process. Not intended

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto schedule status
- **Memory ID**: `64220eca-0a93-4a0e-8c11-4ab64250a520`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `schedule`
- **Content**:
> Run `memanto schedule status` to check the status of the scheduled job.

---

### [2026-09-01 21:25:52] [INSTRUCTION] memanto session info
- **Memory ID**: `f4cae692-2a2e-4b28-baac-941eb5c4d509`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `cli`, `session`
- **Content**:
> Run `memanto session info` to show current active agent activation information.

---

### [2026-09-01 21:25:52] [FACT] agent service
- **Memory ID**: `8b459d15-0b1b-4ab9-a205-061dab4a4bf0`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service agent_service — agent Service for MEMANTO

---

### [2026-09-01 21:25:52] [FACT] conversation memory extraction service
- **Memory ID**: `8e346e41-18c2-4f72-8b11-7cc14458d248`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service conversation_memory_extraction_service — conversation memory extraction service.

---

### [2026-09-01 21:25:52] [FACT] daily analysis service
- **Memory ID**: `aacbe3b6-1c04-49a6-b526-96fdcc941c54`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service daily_analysis_service — daily Analysis Service

---

### [2026-09-01 21:25:52] [FACT] memory export service
- **Memory ID**: `6834fa1a-ecd5-481a-a077-a59bbbc54955`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service memory_export_service — memory Export Service

---

### [2026-09-01 21:25:52] [FACT] memory parsing service
- **Memory ID**: `5ed720d4-3bc2-4571-a72e-54d37e6f0823`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service memory_parsing_service — memory Parsing Service

---

### [2026-09-01 21:25:52] [FACT] memory policy service
- **Memory ID**: `62075ac7-24c7-4175-989d-d1fce2bf6abd`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service memory_policy_service — memory Policy Service

---

### [2026-09-01 21:25:52] [FACT] memory read service
- **Memory ID**: `12db340d-2b43-4c69-883c-cc22d58e5058`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service memory_read_service — memory Read Service

---

### [2026-09-01 21:25:52] [FACT] memory write service
- **Memory ID**: `4f918d9c-47d0-45c9-8b20-63263f0429d2`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service memory_write_service — memory Write Service

---

### [2026-09-01 21:25:52] [FACT] namespace service
- **Memory ID**: `015f72ac-da9d-47de-a3f0-975763965c23`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service namespace_service — namespace Service

---

### [2026-09-01 21:25:52] [FACT] okf export service
- **Memory ID**: `52dfb393-b2c2-45b4-83fc-962a4954539c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service okf_export_service — oKF (Open Knowledge Format) Export Service

---

### [2026-09-01 21:25:52] [FACT] policy presets
- **Memory ID**: `6fbf0da5-de18-4383-87fd-05cadadcdaeb`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service policy_presets — predefined expiry policy bundles.

---

### [2026-09-01 21:25:52] [FACT] session service
- **Memory ID**: `45de5585-ed0b-496b-8f71-aa5b37cbd639`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service session_service — session Service for MEMANTO

---

### [2026-09-01 21:25:52] [FACT] summary visualization service
- **Memory ID**: `5886f8cb-1bc9-4930-a007-baa51f278282`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `services`
- **Content**:
> Service summary_visualization_service — summary Visualization Service

---

### [2026-09-01 21:25:52] [RELATIONSHIP] auth deps
- **Memory ID**: `716bc201-8eb5-4d3a-859d-190506bc4d29`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `routes`
- **Content**:
> Router auth_deps — authentication Dependencies for V2 API

---

### [2026-09-01 21:25:52] [RELATIONSHIP] health
- **Memory ID**: `ef15de78-2efa-4301-ad61-4101745a1d75`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `routes`
- **Content**:
> Router health — health Check Routes

---

### [2026-09-01 21:25:52] [RELATIONSHIP] memory
- **Memory ID**: `e708fd54-281a-4a7e-bd7f-52ddebf421d6`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `routes`
- **Content**:
> Router memory — memory Operations - Session-Based

---

### [2026-09-01 21:25:52] [RELATIONSHIP] sessions
- **Memory ID**: `b851879f-a38f-4e8a-8a78-ca6c1afa88c5`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `routes`
- **Content**:
> Router sessions — session and Agent Lifecycle Routes

---

### [2026-09-01 21:25:52] [ARTIFACT] atomic write
- **Memory ID**: `6672469b-ead1-4d0b-b201-913234ab311c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility atomic_write — crash-safe helpers for replacing small local state files.

---

### [2026-09-01 21:25:52] [ARTIFACT] errors
- **Memory ID**: `caf3abf9-c689-400b-bb62-85817a0c7f9c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility errors — error Handling and Mapping

---

### [2026-09-01 21:25:52] [ARTIFACT] ids
- **Memory ID**: `52d97cfc-8a44-40ff-9f88-5f1cf5b2b913`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility ids — iD Generation Utilities

---

### [2026-09-01 21:25:52] [ARTIFACT] json extraction
- **Memory ID**: `5fa25cbe-d0f1-4974-9ee5-8a2964b25c95`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility json_extraction — helpers for extracting structured JSON from LLM responses.

---

### [2026-09-01 21:25:52] [ARTIFACT] temporal helpers
- **Memory ID**: `8dbb2e74-ef46-4227-ae3f-7ed96f5a1d7a`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility temporal_helpers — temporal Query Helpers

---

### [2026-09-01 21:25:52] [ARTIFACT] validation
- **Memory ID**: `1e126b2a-3f53-4690-882b-bc198bcf57be`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `utils`
- **Content**:
> Utility validation — input Validation and Cost Guards for MEMANTO

---

### [2026-09-01 21:25:52] [FACT] backend
- **Memory ID**: `32777f30-c01e-493a-91d7-7a598fdde0ba`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `clients`
- **Content**:
> Client backend — backend selection and protocol for Memanto's Moorcheh client.

---

### [2026-09-01 21:25:52] [FACT] moorcheh
- **Memory ID**: `ba3b9bf3-bb21-49a4-a5a2-ff8ac6c3b1d4`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `clients`
- **Content**:
> Client moorcheh — moorcheh Client Singleton (backend-aware dispatcher).

---

### [2026-09-01 21:25:52] [FACT] onprem
- **Memory ID**: `338134aa-bb54-44d7-99f2-63c129f7b9fd`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `clients`
- **Content**:
> Client onprem — on-prem Moorcheh client.

---

### [2026-09-01 21:25:52] [OBSERVATION] test analyze
- **Memory ID**: `3d7b16f7-ce59-4b0c-9c12-00903796ab9e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_analyze covers: unit tests for memanto analyze pipeline (no API keys or network).

---

### [2026-09-01 21:25:52] [OBSERVATION] test as of date only parsing
- **Memory ID**: `e47429d0-d04c-4be2-80a6-c783b7e3d195`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_as_of_date_only_parsing covers: regression tests for as-of date-only parsing.

---

### [2026-09-01 21:25:52] [OBSERVATION] test as of expired recall
- **Memory ID**: `cec8904e-2757-4d74-ba0d-518d553ffdcc`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_as_of_expired_recall covers: regression tests for point-in-time (``search_as_of``) recall.

---

### [2026-09-01 21:26:01] [OBSERVATION] test backend
- **Memory ID**: `6d19dd44-fa26-4904-8998-446f8c47e862`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_backend covers: tests for the backend abstraction (cloud vs on-prem dispatcher).

---

### [2026-09-01 21:26:01] [OBSERVATION] test cli
- **Memory ID**: `3ed23f0f-1407-455c-8fdf-67a37a602c5b`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_cli covers: mEMANTO CLI Integration Tests

---

### [2026-09-01 21:26:01] [OBSERVATION] test cli stream encoding
- **Memory ID**: `bcae3841-2485-45af-a1d6-f386c9a2311c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_cli_stream_encoding covers: regression tests for CLI stream encoding.

---

### [2026-09-01 21:26:01] [OBSERVATION] test cors fix
- **Memory ID**: `4f487595-8226-4c47-aaca-0adba4c9b5cc`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_cors_fix covers: tests for CORS misconfiguration fix (#770).

---

### [2026-09-01 21:26:01] [OBSERVATION] test daily analysis query length
- **Memory ID**: `baf108d9-293a-4b3c-aa9b-76129acba386`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_daily_analysis_query_length covers: regression coverage for daily-summary embedding context overflow.

---

### [2026-09-01 21:26:01] [OBSERVATION] test e2e
- **Memory ID**: `fe43748e-3e65-49d2-ab95-6174770c71eb`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_e2e covers: end-to-end tests — real Moorcheh API, zero mocks.

---

### [2026-09-01 21:26:01] [OBSERVATION] test export resilience
- **Memory ID**: `211c5185-0958-4c2c-89da-b8aebacc6315`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_export_resilience covers: regression coverage: ``export_memory_md`` must not silently write an empty export when every ``recall`` call fails (e.g. the on-prem backend is

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse config
- **Memory ID**: `f8526a63-9c08-4c11-a45c-7b08f052fbec`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_config covers: tests for per-project Langfuse capture settings and score rules.

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse discover
- **Memory ID**: `723c8927-011a-47b1-ba09-f5351a05c923`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_discover covers: tests for Langfuse project discovery.

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse export
- **Memory ID**: `7c6446bc-e9fd-4c8b-87c6-572ab7005e03`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_export covers: tests for the Langfuse exporter: credentials, hosts, and cursor pagination.

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse rules
- **Memory ID**: `fba1308c-bde1-4e6d-8162-00d6a6abe24c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_rules covers: tests for Langfuse capture rules: classification, signatures, payloads.

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse state
- **Memory ID**: `13f02988-48ff-48b3-b69c-25b1e9ca5f93`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_state covers: tests for the Langfuse sync ledger — the thing that makes re-syncing safe.

---

### [2026-09-01 21:26:01] [OBSERVATION] test langfuse sync
- **Memory ID**: `0e33caa0-bec7-4f39-8dc9-3dce7f4fcbb6`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_langfuse_sync covers: tests for the shared Langfuse sync path (CLI + UI tile).

---

### [2026-09-01 21:26:01] [OBSERVATION] test memory format
- **Memory ID**: `e06ee905-b3e7-4819-b9af-fbfdc657b269`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_memory_format covers: test memory format round-trip integrity: content/tag parsing in _format_memory_item.

---

### [2026-09-01 21:26:01] [OBSERVATION] test memory policy
- **Memory ID**: `fa6a20e9-7b6e-46f3-9d3a-85ef90bcc5b7`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_memory_policy covers: tests for expiry policies: duration parsing, evaluation, sweeps, purge.

---

### [2026-09-01 21:26:01] [OBSERVATION] test memory read multi type
- **Memory ID**: `0c520a1f-27e3-4f88-936f-652657969e27`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_memory_read_multi_type covers: regression coverage for union semantics in multi-type recall.

---

### [2026-09-01 21:26:01] [OBSERVATION] test memory read temporal recall
- **Memory ID**: `6be51e52-fa13-41d2-b806-a618c2e0d60d`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_memory_read_temporal_recall covers: regression tests for temporal / post-retrieval recall.

---

### [2026-09-01 21:26:01] [OBSERVATION] test migrate
- **Memory ID**: `c1f1faaf-7a0b-4019-a104-f95aef524e6c`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_migrate covers: focused regression tests for migration tools and mappers.

---

### [2026-09-01 21:26:01] [OBSERVATION] test moorcheh user config compat
- **Memory ID**: `3e9a26ee-aab5-4f22-8731-cbee43d1fa32`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_moorcheh_user_config_compat covers: regression tests for the moorcheh-client user_config import path.

---

### [2026-09-01 21:26:01] [OBSERVATION] test okf
- **Memory ID**: `d004e9c2-2896-4170-ab94-b3c94b9b2bc2`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_okf covers: oKF (Open Knowledge Format) export/import coverage.

---

### [2026-09-01 21:26:01] [OBSERVATION] test output path traversal
- **Memory ID**: `38dcace3-2fb1-4b13-80bb-6a49d5ceb99e`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_output_path_traversal covers: tests for output_path traversal fix (#770).

---

### [2026-09-01 21:26:01] [OBSERVATION] test pagination guard
- **Memory ID**: `fb9aedaa-45a1-48c6-af8c-ff173f73f63d`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_pagination_guard covers: regression tests for memory document pagination.

---

### [2026-09-01 21:26:01] [OBSERVATION] test postcommit summary resilience
- **Memory ID**: `7fbe9c01-2ee8-4f3e-9221-0130ef1d62ed`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_postcommit_summary_resilience covers: committed memory operations must not fail on auxiliary summary logging.

---

### [2026-09-01 21:26:01] [OBSERVATION] test remaining ui auth
- **Memory ID**: `ec69d87d-e874-4a4e-8f06-94893be16569`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_remaining_ui_auth covers: tests for the second round of localhost-guarded UI endpoints.

---

### [2026-09-01 21:26:01] [OBSERVATION] test review followups
- **Memory ID**: `52b0edc4-0dd0-4631-93d5-dbf6840299e0`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_review_followups covers: regression tests for issues raised in review of the merged PR batch.

---

### [2026-09-01 21:26:01] [OBSERVATION] test session summary concurrency
- **Memory ID**: `4d621eaf-b7e8-4d36-a6f9-ecc954aa1845`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_session_summary_concurrency covers: concurrency regressions for local session-summary persistence.

---

### [2026-09-01 21:26:01] [OBSERVATION] test title newline roundtrip
- **Memory ID**: `48c6f56b-46a6-42a6-b8f1-b36727b5df1d`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_title_newline_roundtrip covers: regression tests for multi-line memory titles.

---

### [2026-09-01 21:26:01] [OBSERVATION] test ui auth
- **Memory ID**: `86c15a78-78d6-4927-9c72-f37c30d842e3`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_ui_auth covers: tests for unauthenticated UI endpoint vulnerability fix.

---

### [2026-09-01 21:26:01] [OBSERVATION] test unit
- **Memory ID**: `400316de-ddd6-4c9e-935d-35110f5079ad`
- **Confidence**: `0.8`
- **Status**: `active`
- **Source**: `repo-scan`
- **Provenance**: `validated`
- **Tags**: `tests`
- **Content**:
> test_unit covers: mEMANTO Core Unit Tests (No Server Required)

---

