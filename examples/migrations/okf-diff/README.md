# OKF bundle diff

See what changed between two portable agent-memory bundles before you import,
merge, or commit them.

The tool compares parsed OKF entries rather than filenames. It therefore works
across one-file-per-memory and stacked-per-type layouts. Entries match by
`x_memanto.id` when present, then `resource`, then normalized type and title.

It runs locally and does not require a Moorcheh API key.

## Try the included example

From the repository root:

```bash
uv run python examples/migrations/okf-diff/okf_diff.py \
  examples/migrations/okf-diff/samples/before \
  examples/migrations/okf-diff/samples/after \
  --html /tmp/okf-diff.html \
  --markdown /tmp/okf-diff.md \
  --json /tmp/okf-diff.json
```

Expected summary:

```text
4 -> 4 entries | 1 added | 1 removed | 1 changed | 2 unchanged
```

Open `/tmp/okf-diff.html` in a browser. The report is a standalone file with
search, status filters, and side-by-side field values. It has no external
assets or network requests.

## Use it as a CI gate

Fail when any semantic memory changes:

```bash
uv run python examples/migrations/okf-diff/okf_diff.py \
  ./baseline-okf ./candidate-okf --fail-on-change
```

Fail only when memories disappear:

```bash
uv run python examples/migrations/okf-diff/okf_diff.py \
  ./baseline-okf ./candidate-okf --fail-on-removal
```

Exit status `0` means the selected gate passed, `1` means it detected a gated
change, and `2` means the input could not be loaded.

## What the reports contain

| Output | Use |
| --- | --- |
| Terminal | Compact count for local scripts and CI logs |
| JSON | Machine-readable entry and field changes |
| Markdown | Review artifact with unified body patches |
| HTML | Searchable local viewer for human inspection |

The semantic comparison covers OKF baseline fields, Memanto's `x_memanto`
extension, unknown frontmatter fields, extracted links, and the Markdown body.
Navigation files are skipped by Memanto's existing OKF loader.

## Identity and duplicate handling

The matching order is:

1. `x_memanto.id`
2. `resource`
3. normalized `type` plus `title`

When a bundle contains duplicate identities, exact payload matches pair first.
Remaining entries pair deterministically and receive `#1`, `#2`, and later
suffixes in the report. No entry is silently discarded.

## Tests

```bash
uv run pytest examples/migrations/okf-diff/tests -q
uv run ruff check examples/migrations/okf-diff
uv run ruff format --check examples/migrations/okf-diff
```

The tests cover added, removed, changed, unchanged, layout-only moves, duplicate
identities, stacked OKF files, report generation, and both CI exit gates.
