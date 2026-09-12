# Codex → OKF memory bundle

Portable, human-readable export of an OpenAI Codex CLI memory store.

Import it into Memanto:

```bash
memanto migrate okf . --dry-run
memanto migrate okf .
```

Every document under `memories/<type>/` is one memory: YAML frontmatter +
Markdown body. `x_memanto.type` carries the authoritative Memanto memory
type; the top-level `type` preserves the original Codex concept.
