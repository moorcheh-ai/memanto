# Cursor Notes

Open the repository root in Cursor, then focus on:

- `examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py`
- `examples/crewai_memanto_memory_demo/README.md`
- `examples/crewai_memanto_memory_demo/demo_transcript.txt`

Safe prompt to extend the demo:

```text
Improve the CrewAI + Memanto demo without changing repo-wide config. Keep all
changes inside examples/crewai_memanto_memory_demo. Preserve the real Memanto
SDK/service integration, keep credentials in environment variables, and update
README.md plus SUBMISSION_NOTES.md for any behavior changes.
```

How Cursor can use Memanto notes for this project:

1. Run the store phase after setting `MOORCHEH_API_KEY`.
2. Ask Cursor to inspect the recalled context from the terminal output.
3. If you add a new scenario, store the decision or outcome with
   `memory_type="decision"` or `memory_type="artifact"`.
4. Keep any generated `.env`, casts, logs, or recordings out of git unless they
   are intentional documentation artifacts.

No global Cursor configuration is required for this bonus. This file is scoped
to the example so it does not affect contributors who do not use Cursor.
