# Round-trip validation report

Generated: 2026-08-07T05:54:23.445239+00:00
Source: Qdrant collection 'memories' (61 records)
Mapped: 61 memories -> 61 re-imported from OKF bundle

## Record-level round-trip parity

Keys records by `source_ref` (record identity) and checks content continuity.
Type re-classification on import is expected (OKF types are free-form) and reported, not failed.

| Check | Result |
| --- | --- |
| Source records | 61 |
| Re-imported records | 61 |
| Missing (source_ref in source, absent in bundle) | 0 |
| Extra (source_ref only in bundle) | 0 |
| Rows whose content body was lost | 0 |
| Re-classified on import | 0 |
| **Record parity** | **PASS** |

## Golden QA (recall parity)

| Question | Expected | Found in bundle |
| --- | --- | --- |
| Where does Tim live? | lisbon | YES |
| What is Tim's cat's name? | pixel | YES |
| What embedding store does the team use? | qdrant | YES |
| What is the preferred backend language? | python | YES |
| What coffee does Tim order? | flat white | YES |

**Recall parity: 5/5 (100%)**

## Artifacts

- `export.json` — raw Qdrant collection dump (provider-style export)
- `mapped_preview.jsonl` — mapped Memanto memory payloads
- `okf_bundle/` — valid OKF bundle (index.md + memories/)