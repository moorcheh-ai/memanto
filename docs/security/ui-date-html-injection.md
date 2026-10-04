# External date metadata rendered as UI markup

This finding continues the existing #1852 submission. It demonstrates HTML
injection from an externally written memory date into the recall/explorer
table. It does not demonstrate a browser event handler, hosted backend
exploit, unauthenticated write, or cross-agent access.

## Affected boundary

`memanto/app/ui/static/index.html` has Git blob
`80cfd734cce86730128ea83427f72f5eb66ba3a3` on both the reviewed upstream source
and the existing carrier branch. Its `fmtDate` helper returns malformed date
strings unchanged. `buildMemoryTable` inserts the created-date result into
an HTML template without escaping, and the recall/explorer views assign that
template to `innerHTML`.

The storage read path deliberately supports records written outside Memanto:

- The module-level `_coerce_timestamp_str` in
  `memanto/app/services/memory_read_service.py` preserves every string.
- `_format_memory_item` prefers a non-null nested metadata field over its flat
  counterpart and applies that coercer to `created_at`.
- The `MemoryItem` response model accepts `created_at` as `str | None`; it does
  not require the string to parse as a date.
- The recall and recent-recall endpoints return those formatted records.
  `doRecall` renders the response with `buildMemoryTable`; `loadExplorer`
  passes it through `renderExplorer` to the same renderer.

The backend trace was pinned to carrier head
`89b4e4c69ff88fbd674c212c6e87dea1da4e81cd`. The read-service blob is
`31e6870cef3f2693919fc1a8110bf078c6abd9ad`; the response-model blob is
`236f1a9c92381f192336dc3182bc9c90f8cf502e`.

## Controlled reproduction

Use a valid external document envelope containing a normal title/body and a
nested date field such as:

```json
{
  "id": "local-render-probe",
  "text": "[FACT] Normal title\n\nNormal memory body",
  "memory_type": "fact",
  "confidence": 0.8,
  "created_at": "2026-10-04T07:00:00Z",
  "metadata": {
    "agent_id": "local-agent",
    "created_at": "<img src=x data-memanto-probe=\"date\">"
  }
}
```

The exact extracted production coercer and formatter preserve the nested
string, and the actual `MemoryItem` model accepts it. This component run used
the valid-envelope path; it did not write to storage or start the API server.
The full reader module could not be imported in the minimal observation
environment because its unrelated HTTP/configuration dependencies were not
installed, so those production functions were extracted from its Python AST
without changing their behavior.

The actual source `fmtDate`, `escHtml`, `buildMemoryTable` and supporting
functions were then executed in Node. A small text-element adapter delegated
the `textContent` to `innerHTML` serialization to lxml. Parsing the returned
table with lxml produced one unexpected `img` element. After the repair it
produced zero, and the complete marker appeared as literal visible text.
Normal ISO and missing-date control outputs were byte-for-byte unchanged.

No browser was launched and no HTML event handler was executed.

## Repair and regression

Use the existing `escHtml` helper at the remaining HTML date substitutions:
the memory and agent tables, dashboard profiles, history scan reason,
migration preview, and session timeline. Keep `fmtDate` returning plain text
for its DOM/text callers and preserve the already escaped date displays.

The migration preview was also exercised with the controlled renderer input.
Its image count changed from one to zero. This is a defense at the rendering
boundary: the current real migration path parses source dates and serializes
them with `isoformat`, so the experiment does not establish an injection
through ordinary migration inputs. The other date substitutions apply the
same text-escaping rule; their full views were not executed.

Run the focused manual regression with the existing Python and Node runtimes:

```bash
python tests/ui_date_rendering.py
```

It uses only their standard libraries, extracts the real UI functions, and
checks eight rendered cases: four date values in memory and migration output.
The text-element adapter uses ElementTree serialization; HTMLParser checks
the resulting elements and text. The cases cover the image marker, valid and
missing dates, and malformed text containing `&` and angle brackets. They
also check that `fmtDate` remains plain text and the previously escaped
updated-date display is preserved. This command is explicit rather than a
silently skipped pytest test. It passed on the repaired source; selecting the
original HTML as its first argument failed on the injected table image. The
complete inline UI script also passed Node syntax compilation.

## Preconditions and limits

An external writer must already be able to place a record in the configured
agent namespace, or the namespace must already contain malformed legacy data.
Ordinary remember and batch operations construct timestamped `MemoryRecord`
objects and do not provide this arbitrary-date input path. Session-token and
agent-scope authorization remain in force.

The record must appear in the returned result window. Recent recall sorts an
invalid date behind valid dates, and active temporal bounds exclude malformed
dates. The repair changes rendering only; it does not claim a new storage
permission, authentication bypass, completed bounty award, or payment.
