# Escape Antigravity: native brain archives → Memanto OKF

This Path B showcase migrates a real Google Antigravity desktop session from
its native local `~/.gemini/antigravity/brain/` archive into readable,
git-friendly [Open Knowledge Format (OKF)](https://docs.memanto.ai/integrations/okf)
Markdown. It then feeds that bundle through Memanto's shipped OKF importer and
reconstructs every source artifact byte-for-byte.

```text
Antigravity brain archive → readable OKF → Memanto → exported OKF
           ↑                                      ↓
           └──── exact artifact reconstruction ───┘
```

This is not the generic Gemini web conversation-export route. Antigravity's
desktop agent writes an evolving “brain” beside its conversation store:
implementation plans, walkthroughs, task artifacts, numbered revisions, and
visual evidence. This adapter turns that native agent history into durable
memory while keeping opaque conversation bytes and private images out of the
public bundle.

## Real-data provenance

The checked-in sample comes from an actual Antigravity desktop session run on
November 19, 2025. The session iterated through several dashboard directions
before converging on a Tensor-Green ASCII design. It contains:

- 2 canonical artifacts: an implementation plan and final walkthrough;
- 9 numbered historical revisions, preserving how the plan and result evolved;
- 15 image artifacts recorded by filename, byte size, and SHA-256 only;
- one 3,560,058-byte opaque conversation `.pb`, recorded by SHA-256 and entropy
  only—its private bytes are never copied or decoded.

`prepare_public_sample.py` produced the sample directly from the real archive.
It pseudonymized the conversation ID and redacted 40 local-path occurrences
and five URL occurrences across the canonical artifacts and their revisions.
The redaction report and the opaque source hash are committed in
`sample/source/source-provenance.json`; the source was not hand-written to look
like an export.

## One-command offline demo

From the Memanto repository root:

```bash
uv sync --group dev
uv run python examples/migrations/antigravity-brain/run_demo.py
```

The command:

1. reads the real, de-identified Antigravity archive;
2. writes one importable OKF memory per native brain artifact/revision;
3. calls the shipped `memanto migrate okf ... --dry-run` command;
4. loads and maps the bundle through Memanto's real Python implementation;
5. reconstructs the exact source Markdown and metadata bytes;
6. validates three golden questions and nine expected phrases.

No key, network request, or cloud write is needed for this path. Expected
headline result:

```text
source artifacts:                  11
OKF memories mapped:               11 (0 skipped)
type breakdown:                    event 9, goal 1, learning 1
source files reconstructed exactly: 13/13
golden phrase retention:            9/9 (100%)
Memanto CLI dry-run:                passed
```

## Migrate your own Antigravity archive

Preview a private, lossless bundle:

```bash
uv run python examples/migrations/antigravity-brain/migrate_antigravity.py \
  ~/.gemini/antigravity ./my-antigravity-okf

memanto migrate okf ./my-antigravity-okf --dry-run
```

Limit the migration to one conversation:

```bash
uv run python examples/migrations/antigravity-brain/migrate_antigravity.py \
  ~/.gemini/antigravity ./my-antigravity-okf \
  --conversation <conversation-id>
```

For a shareable bundle, enable deterministic privacy controls and optionally
provide exact custom replacements as a JSON object:

```bash
uv run python examples/migrations/antigravity-brain/migrate_antigravity.py \
  ~/.gemini/antigravity ./public-antigravity-okf \
  --conversation <conversation-id> \
  --publishable \
  --redactions ./my-private-redactions.json
```

Publication mode redacts emails, URLs, absolute home paths, IP addresses,
UUIDs, and common secret assignments. It also replaces the local conversation
ID with a stable hash alias. Always review a generated bundle before sharing
it; project prose may still be sensitive even when credentials and paths are
gone.

## Mapping and fidelity

| Antigravity source concept | Memanto type | OKF representation |
| --- | --- | --- |
| Current task | `commitment` | Readable Markdown memory |
| Current implementation plan | `goal` | Readable Markdown memory |
| Current walkthrough | `learning` | Readable Markdown memory |
| Numbered plan/walkthrough revision | `event` | Ordered historical memory |
| Unknown brain artifact | `artifact` | Readable Markdown memory |
| Artifact metadata sidecar | Source marker | Compressed exact bytes |
| Opaque conversation `.pb` | Provenance report | Hash, size, entropy; no contents |
| Image/video artifact | Attachment report | Hash, size, filename; no binary copy |

Each OKF document contains the source text as normal Markdown. A compact hidden
`antigravity-source-v1` marker carries a zlib-compressed copy of the exact
source chunk and metadata sidecar. The marker survives Memanto import/export,
allowing `reconstruct_antigravity.py` to rebuild original bytes even though the
Memanto mapper appends its own supporting-data footer.

Artifacts are split into size-safe chunks before reaching Memanto's 10,000
character memory limit. The reconstructor validates part counts, content
hashes, duplicate paths, and traversal attempts, then fails closed on any
mismatch.

## Honest storage report

Antigravity brain artifacts are local files, so there is no provider billing,
token, or latency baseline. The adapter reports those savings as unavailable
instead of inventing them.

For the real checked-in sample, 23,515 bytes of source Markdown and metadata
become 55,488 bytes of importable OKF. The 31,973-byte increase is deliberate
portability overhead: human-readable frontmatter plus compressed source
markers that make exact reconstruction possible.

## Cloud-backed freedom loop

`run_live_demo.py` previews its full command plan by default and performs no
writes:

```bash
uv run python examples/migrations/antigravity-brain/run_live_demo.py
```

After setting `MOORCHEH_API_KEY` locally, execute the live route:

```bash
uv run python examples/migrations/antigravity-brain/run_live_demo.py \
  --output ./antigravity-live-evidence \
  --execute
```

The guarded route creates a dedicated agent, imports all 11 memories, runs the
three golden questions through `recall` and `answer`, exports the live agent to
OKF, and reconstructs all 13 source files from that export. Use `--reuse-agent`
only when intentionally appending to an existing dedicated demo agent, or
`--skip-answers` when the configured answer model is unavailable.

The script never prints the API key. It stages the export under Memanto's own
data directory to satisfy the CLI's output-path guard, copies it into a fresh
evidence directory, and removes the staging copy in a `finally` block.

## Output layout

```text
sample/
├── golden_qa.json
├── source/
│   ├── brain/session-…/            # 11 de-identified real artifacts
│   └── source-provenance.json      # hashes, entropy, redaction evidence
└── okf/
    ├── index.md
    ├── memories/
    │   ├── event/                  # 9 historical revisions
    │   ├── goal/                   # current implementation plan
    │   └── learning/               # current walkthrough
    └── metrics/
        ├── mapping-table.md
        ├── memanto-cli-dry-run.json
        ├── migration-report.json
        ├── privacy-report.json
        ├── round-trip-validation.json
        ├── savings-report.json
        └── source-provenance.json
```

## Reconstruct an export

The same command works on the original generated bundle or on an OKF bundle
exported back out of Memanto:

```bash
uv run python examples/migrations/antigravity-brain/reconstruct_antigravity.py \
  ./exported-okf ./reconstructed-antigravity
```

## Tests

```bash
uv run pytest -q examples/migrations/antigravity-brain/tests
uv run ruff check examples/migrations/antigravity-brain
uv run ruff format --check examples/migrations/antigravity-brain
```

The focused suite covers native discovery, revision handling, real Memanto OKF
mapping, exact reconstruction, long-artifact chunking, publication redaction,
payload tampering, path traversal, and safe output replacement.

## Privacy boundary

The adapter deliberately does not reverse engineer or decrypt Antigravity's
opaque conversation `.pb` files. Their near-8-bit entropy is reported as an
observation, not proof of a particular encryption scheme. Native brain
artifacts are the supported migration surface because they are readable,
versioned outputs intended for human review. Raw conversation files and binary
screenshots remain local unless a user handles them separately.
