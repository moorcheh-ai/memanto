# Sample provenance

This fixture is a privacy-redacted extract of Claude Code state created by
real planning sessions for the Auto Planmaxxer project. Claude Code itself
created the source memory documents and prompt-history rows during normal use;
they were not authored as fake migration inputs.

## Included source

- two durable auto-memory documents from the project's `memory/` directory;
- the generated `MEMORY.md` navigation index; and
- three ordered prompts from one real project session in `history.jsonl`.

The small fixture is deliberate: it is large enough to exercise different
Claude memory types, grouped session history, timestamps, stable references,
redaction, OKF export, Memanto dry-run mapping, and recall parity while
remaining fully inspectable in a pull request.

## Privacy transformation

Before committing the fixture:

- the local username and project root were replaced with
  `/Users/demo/Projects/auto-planmaxxer`;
- unrelated projects and sessions were omitted;
- session content was limited to non-sensitive project-planning prompts;
- transcripts, tool payloads, attachments, file snapshots, environment
  captures, and todos were omitted; and
- the committed files were scanned for the original home path, email
  addresses, and common credential shapes.

The meaning, ordering, source kinds, and timestamps of the included records
were preserved. The adapter performs its own second redaction pass when
generating OKF, so the committed output contains `${HOME}` rather than the
fixture's local directory.

For a truly lived-in migration, run the same adapter against your own
`~/.claude` directory as documented in the parent README.
