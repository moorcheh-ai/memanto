# Static Audit Notes (Hardening, non-bug)

Companion to `770-security-audit-fixes.md`. These were found during the same
static audit but are **architectural/UX decisions or low-confidence items**
rather than clear bugs, so they are recorded here as hardening notes for a
possible follow-up.

## 1. Contradiction detection matches only on `title`

`_find_contradictions` (`memory_validation_service.py`) searches active
same-agent/same-type candidates and filters on
`item.title.strip().lower() == title_key`, treating identical `content` as a
duplicate (not a contradiction). This means:

- Memories with different titles but identical content are silently stored as
  separate records.
- Semantically opposed memories with different titles are not flagged.

This is a design limitation of the title-keyed index, not a defect — the module
documents the matching rule. A future improvement would add a content/semantic
similarity pass feeding the manual-conflict report, without changing the
existing title-key semantics.

## 2. `get_data_dir` backend-directory heuristic

`config.get_data_dir()` isolates on-prem data into `~/.memanto/on-prem/` when
`MEMANTO_BACKEND.strip().lower() == "on-prem"`, while `parse_backend()` in
`clients/backend.py` does the same normalization separately. The two
normalisations are currently aligned; a tiny whitespace/case mismatch could in
theory make the data dir diverge from the selected backend. Risk is low
(config robustness) and does not affect a default deployment. A follow-up
could centralise the heuristic into `parse_backend()`.
