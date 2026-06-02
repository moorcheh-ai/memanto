# Memanto Bridge For Developer Skills

This example adds a small memory bridge around developer skill commands. It is designed for teams using single-purpose skills such as `/grill-with-docs`, `/tdd`, `/handoff`, and `/diagnose`, where useful decisions often get trapped in one run and then have to be repeated in the next.

The bridge does two things:

- Before a skill starts, it recalls relevant engineering memories and prints a compact prompt block.
- After a skill finishes, it reads the transcript, extracts durable decisions and preferences, and stores them.

It runs without credentials by default using a local JSONL file. A live Memanto backend can be enabled later with an environment variable and a Moorcheh key.

## What Is Included

```text
examples/claudecode-skills-memanto/
|-- README.md
|-- demo-transcript.md
|-- .env.example
|-- pyproject.toml
|-- validate.py
|-- src/skill_memanto_bridge/
|   |-- __init__.py
|   |-- backends.py
|   |-- bridge.py
|   |-- cli.py
|   `-- wrappers.py
`-- tests/
    `-- test_bridge.py
```

## Install

From this folder:

```bash
python -m pip install -e .
```

Offline validation does not need the package to be installed:

```bash
python validate.py
```

## Local Backend

Local mode is the default. It writes JSONL records to:

```text
~/.memanto/skill-memory/developer-skills.jsonl
```

Override it when testing:

```bash
export SKILL_MEMANTO_STORE=/tmp/developer-skills.jsonl
```

PowerShell:

```powershell
$env:SKILL_MEMANTO_STORE = "$env:TEMP\developer-skills.jsonl"
```

Each record stores a title, content, memory type, confidence, tags, source skill, task, path, and timestamp. No secrets are required for this mode.

## Live Memanto Backend

Live mode is opt-in:

```bash
export SKILL_MEMANTO_BACKEND=live
export MOORCHEH_API_KEY=your-key-here
export SKILL_MEMANTO_AGENT_ID=developer-skills
```

PowerShell:

```powershell
$env:SKILL_MEMANTO_BACKEND = "live"
$env:MOORCHEH_API_KEY = "your-key-here"
$env:SKILL_MEMANTO_AGENT_ID = "developer-skills"
```

When live mode is enabled, the bridge lazily imports `memanto.cli.client.sdk_client.SdkClient` and calls its `remember` and `recall` methods. If live mode is not enabled, no Memanto package import or network call is attempted.

## Manual Hook Usage

Print context before a skill:

```bash
python -m skill_memanto_bridge.cli pre-run \
  --skill tdd \
  --task "Add payment webhook tests" \
  --path services/payments/webhooks.py
```

Save memories after a skill:

```bash
python -m skill_memanto_bridge.cli post-run \
  --skill grill-with-docs \
  --task "Plan payment webhook handling" \
  --path services/payments/webhooks.py \
  --transcript-file transcript.txt
```

If `--transcript-file` is omitted, `post-run` reads from standard input.

## Wrapper Generation

Generate launchers for common skills:

```bash
python -m skill_memanto_bridge.cli generate-wrappers \
  --output-dir .memanto-skill-wrappers \
  tdd grill-with-docs handoff diagnose
```

Each generated wrapper has a shell version and a PowerShell version. The wrapper needs an environment variable that points to the real command it should run.

Example shell setup:

```bash
export SKILL_MEMANTO_TDD_COMMAND="claude /tdd"
.memanto-skill-wrappers/tdd "Add payment webhook tests"
```

Example PowerShell setup:

```powershell
$env:SKILL_MEMANTO_TDD_COMMAND = "claude /tdd"
.\.memanto-skill-wrappers\tdd.ps1 "Add payment webhook tests"
```

This avoids hard-coding a specific terminal tool while still giving reviewers a concrete, installable wrapper path.

## Extraction Rules

The offline extractor is intentionally conservative. It stores lines that look like durable engineering guidance:

- decisions: `We decided to keep webhook verification in app/security.py.`
- preferences: `Preference: use stdlib hmac before adding dependencies.`
- instructions: `Avoid storing provider secrets in logs.`

It skips general conversation, caps the number of saved items per run, and redacts common key, token, password, and long-secret patterns before writing.

## Validation

Run:

```bash
python validate.py
```

The script runs:

- `python -m unittest discover -s tests -v`
- `compileall` over `src`, `tests`, and `validate.py`
- a blocked-term scan for this example folder

## Why This Fits The Challenge

The bridge is useful without setup, but it still has a clean path to live Memanto:

- credential-free local JSONL backend for reviewer-safe testing
- optional live `SdkClient` backend through environment variables
- pre-run dynamic injection
- post-run active extraction
- generated wrappers for skill commands
- demo transcript
- focused offline tests
- no private keys or external services needed for validation
