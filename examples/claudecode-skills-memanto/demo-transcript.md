# Demo Transcript

This transcript shows the intended reviewer flow using the local JSONL backend. It uses fake project details and no private keys.

## 1. Install

```bash
$ cd examples/claudecode-skills-memanto
$ python -m pip install -e .
```

## 2. First Skill Run Stores Decisions

```bash
$ cat > /tmp/grill-transcript.txt <<'EOF'
We decided to keep payment webhook verification in app/security.py.
Preference: use stdlib hmac before adding dependencies.
Avoid storing provider secrets in logs.
EOF

$ python -m skill_memanto_bridge.cli post-run \
    --skill grill-with-docs \
    --task "Plan payment webhook handling" \
    --path services/payments/webhooks.py \
    --transcript-file /tmp/grill-transcript.txt
saved 3 memory item(s)
```

Local JSONL now contains three durable engineering memories:

```json
{"memory_type": "decision", "title": "keep payment webhook verification in app/security.py", "source": "skill:grill-with-docs"}
{"memory_type": "preference", "title": "use stdlib hmac before adding dependencies", "source": "skill:grill-with-docs"}
{"memory_type": "instruction", "title": "Avoid storing provider secrets in logs", "source": "skill:grill-with-docs"}
```

## 3. Later Skill Run Gets Context Automatically

```bash
$ python -m skill_memanto_bridge.cli pre-run \
    --skill tdd \
    --task "Add payment webhook tests" \
    --path services/payments/webhooks.py
<!-- memanto-skill-memory:start -->
### Memanto memory context
Apply these previous engineering decisions if they are relevant:
- [decision] keep payment webhook verification in app/security.py: We decided to keep payment webhook verification in app/security.py.
- [preference] use stdlib hmac before adding dependencies: Preference: use stdlib hmac before adding dependencies.
- [instruction] Avoid storing provider secrets in logs: Avoid storing provider secrets in logs.
<!-- memanto-skill-memory:end -->
```

The second skill run now receives the earlier architecture choice, implementation preference, and logging rule without the developer repeating them.

## 4. Wrapper Flow

```bash
$ python -m skill_memanto_bridge.cli generate-wrappers \
    --output-dir .memanto-skill-wrappers \
    tdd grill-with-docs
.memanto-skill-wrappers/tdd
.memanto-skill-wrappers/tdd.ps1
.memanto-skill-wrappers/grill-with-docs
.memanto-skill-wrappers/grill-with-docs.ps1

$ export SKILL_MEMANTO_TDD_COMMAND="claude /tdd"
$ .memanto-skill-wrappers/tdd "Add payment webhook tests"
```

The wrapper prints memory context first, runs the configured underlying skill command, captures the output transcript, and writes extracted memories after the run.
