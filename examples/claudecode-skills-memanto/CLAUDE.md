## Memanto Memory

Before running ANY skill, always execute:

```bash
memanto-skills recall <skill-name> --hint "<brief task description>"
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
memanto-skills store <skill-name> "<insight>" --type <type>
```

Where `<type>` is one of: `instruction`, `decision`, `preference`, `learning`, `fact`, `artifact`, `goal`.

### Available commands

```bash
memanto-skills recall <skill> [--hint TEXT] [--limit N]
memanto-skills store <skill> "<summary>" [--type TYPE] [--confidence 0.0-1.0]
memanto-skills store-file <skill> <path> [--split]
memanto-skills profile
memanto-skills clear-agent
```
