# Submission Notes

## Files Added

- `crewai_memanto_memory_demo.py`: runnable CLI demo for store, recall, update,
  and full-demo phases.
- `README.md`: setup, run commands, expected output, recording instructions, and
  CrewAI memory swap guide.
- `requirements.txt`: optional demo dependency on CrewAI and dotenv.
- `.env.example`: safe environment variable template with no secrets.
- `demo_transcript.txt`: exact command flow and expected terminal proof shape.
- `CURSOR.md`: Cursor bonus guidance for opening and extending the example.

## What Changed And Why

The change is scoped to a new example folder. It does not alter Memanto core
behavior. The example uses Memanto's real SDK client and service layer to store
and recall memories, then shows how a CrewAI task can be hydrated with recalled
Memanto context.

## Bounty Criteria Mapping

- Working script: `crewai_memanto_memory_demo.py` exposes `--phase store`,
  `--phase recall`, `--phase update`, and `--phase full-demo`.
- Memory test: the store and recall phases are separate commands. The recall
  phase re-instantiates the adapter and prints that it does not use Session 1
  Python variables.
- Visual proof support: `README.md` and `demo_transcript.txt` include the exact
  Loom/Asciinema command sequence to record.
- How-to README: the README includes before/after CrewAI memory code and the
  Memanto recall-before-task, remember-after-task adapter pattern.
- Contradictory memories bonus: `--phase update` stores an old preference,
  stores a corrected preference with supersession metadata, and recalls current
  preferences.
- Cursor bonus: `CURSOR.md` explains safe Cursor usage without repo-wide config.

## Commands Run During Testing

Local environment: Windows PowerShell, Python 3.11.0.

```bash
python -m compileall examples/crewai_memanto_memory_demo
```

Result: passed after allowing normal bytecode atomic writes. The sandboxed
attempt failed because Windows rename operations were blocked.

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --help
```

Result: passed. The CLI showed `--phase`, `--namespace`, `--topic`,
`--simulate-24h`, `--use-real-crewai`, and `--limit`.

```powershell
$env:MOORCHEH_API_KEY='';
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store
```

Result: expected graceful setup failure. The script printed instructions for
setting `MOORCHEH_API_KEY` and did not show a stack trace.

```bash
python -m ruff check examples/crewai_memanto_memory_demo
```

Result: not run. `ruff` is not installed in this Python environment.

```bash
pytest
python -m pytest
```

Result: not run. `pytest` is not installed in this Python environment.

Credentialed commands not run in this environment because `MOORCHEH_API_KEY` is
not configured:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --simulate-24h
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase update
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase full-demo
```

## Known Limitations

- A real `MOORCHEH_API_KEY` is required to prove cloud-backed Memanto storage
  and recall.
- `OPENAI_API_KEY` is required only for `--use-real-crewai`.
- The deterministic mode proves the memory layer and agent handoff without LLM
  spend.
- The high-level Memanto CLI does not expose every supersession metadata field,
  so the demo uses the real lower-level Memanto `MemoryRecord` and
  `MemoryWriteService` for corrected memory metadata.
- Visual proof still must be recorded manually after credentials are configured.

## What Must Not Be Claimed

- Do not claim the Loom/Asciinema proof is complete until the recording link is
  added.
- Do not claim LLM-backed CrewAI kickoff was tested unless
  `--use-real-crewai` was run with an LLM key.
- Do not claim real Memanto storage/recall passed unless the store, recall, and
  update phases were run with a valid `MOORCHEH_API_KEY`.
