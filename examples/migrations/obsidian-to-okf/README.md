# Obsidian vault → Memanto → portable OKF

Watch the [112-second end-to-end demo](./demo.mp4): a real 21-note Obsidian
vault is dry-run mapped, imported into a live Memanto agent, recalled with three
semantic questions, exported back to OKF, and reloaded with zero skipped items.

This example turns an existing Obsidian vault into an OKF v0.2 bundle that
Memanto can inspect with `--dry-run` and import with `memanto migrate okf`.
Conversion is local and deterministic: private vault content never needs an LLM.

## Why this path matters

Obsidian users already own Markdown, but Obsidian-specific wikilinks, embeds,
application frontmatter, and missing memory types limit portability. This adapter:

- preserves every non-empty Markdown note and its original frontmatter;
- converts only unambiguous, resolvable `[[wikilinks]]` and keeps dead links visible;
- maps explicit or conventional note semantics onto Memanto's 13 memory types;
- records source paths, source hashes, provenance, and an honest migration receipt;
- writes a bundle accepted by Memanto's shipped OKF loader and mapper.

## Reproduce in one command

From the repository root:

```bash
python examples/migrations/obsidian-to-okf/run_demo.py
```

The command migrates the checked-in 21-note Inkswell Obsidian vault, validates
the output with Memanto production code, runs three golden recall checks, and
writes `sample-okf/validation-report.json`.

To preview your own vault without writing files:

```bash
python examples/migrations/obsidian-to-okf/obsidian_to_okf.py \
  /path/to/vault /path/to/output --dry-run
```

Then use the shipped toolchain:

```bash
memanto migrate okf /path/to/output --dry-run
memanto migrate okf /path/to/output --agent my-agent
memanto memory export --okf --output /path/to/portable-export
```

## Mapping table

| Obsidian signal | Memanto type | OKF preservation |
|---|---|---|
| Existing supported `type` | Same type | `type`, `x_memanto.type` |
| Inkswell `codex` entity | `fact` | Body plus all source frontmatter |
| Inkswell `longform` project | `goal` | Body plus project schema |
| Draft folder | `artifact` | Original prose and path |
| Plan filename | `decision` | Planning body and metadata |
| Decisions/goals/daily/etc. folder or tag | Matching semantic type | Tags and metadata |
| No semantic signal | `context` | No invented classification detail |

## Real-data evidence

`sample-source-vault/` is the complete public sample vault from
[`leethobbit/obsidian-inkswell-plugin`](https://github.com/leethobbit/obsidian-inkswell-plugin)
at commit `e49b3a0e87576938950ef82289603b809dc24a82`. It contains a lived-in
fiction project with project metadata, 12 scene drafts, seven linked Codex
entities, aliases, custom frontmatter, and intentional dead-link examples. It is
MIT licensed; attribution is preserved in `THIRD_PARTY_LICENSE` and
`SOURCE_PROVENANCE.md`.

The test suite verifies dry-run safety, output-path safety, frontmatter
preservation, link behavior, and production Memanto import compatibility:

```bash
pytest examples/migrations/obsidian-to-okf/tests -q
ruff check examples/migrations/obsidian-to-okf
ruff format --check examples/migrations/obsidian-to-okf
```

## Verified live round trip

On 2026-09-08, the checked-in bundle was imported into a dedicated live
Moorcheh-backed Memanto agent with the shipped CLI. All 21 records imported in
one batch with zero failures. The three golden semantic queries returned the
expected source memory first, and `memanto memory export --okf` produced the
checked-in [`round-trip-okf/`](round-trip-okf/) bundle in 8.05 seconds. Loading
that exported bundle again mapped all 21 records with the same type counts.

See [`LIVE_EVIDENCE.md`](LIVE_EVIDENCE.md) for commands, measured results, and
the explicit reason an OKF import has no provider savings report.

## Limitations

- Ambiguous or missing wikilinks stay untouched and are listed in the report.
- Obsidian Canvas and plugin databases are excluded; this adapter migrates Markdown.
- Memanto's production OKF mapper intentionally bounds unknown supporting-data
  values. Full nested Obsidian extensions remain in `sample-okf/`; long values
  can be abbreviated in the post-Memanto `round-trip-okf/` artifact.
