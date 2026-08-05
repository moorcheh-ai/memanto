## Memanto Memory

Before running ANY skill, always execute:

```bash
claudecode-memanto recall <skill-name> --hint "<brief task description>"
```

Read the output carefully. It contains your persistent engineering profile:
- `[instruction]` entries are **hard rules** — always follow them, no exceptions
- `[decision]` entries are **past choices** — do not re-ask or re-litigate them
- `[preference]` entries are **style choices** — honour them unless technically impossible

If no memories are returned, proceed normally.

After completing ANY skill, ask the user:
> "Anything from this session worth saving to your engineering profile?"

If yes, run:

```bash
claudecode-memanto store <skill-name> "<insight>" --type <type>
```

Where `<type>` is one of: `instruction`, `decision`, `preference`, `learning`, `fact`, `artifact`, `goal`.

### Available commands

```bash
claudecode-memanto recall <skill> [--hint TEXT] [--limit N]
claudecode-memanto store <skill> "<summary>" [--type TYPE] [--confidence 0.0-1.0]
claudecode-memanto store-file <skill> <path> [--split]
claudecode-memanto profile
claudecode-memanto clear-agent
```
