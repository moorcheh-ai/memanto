# Hermes Holographic migration report

## Migration summary

- Source tool: **Hermes Holographic MemoryStore**
- Source facts: **72**
- Exported OKF memories: **72**
- Skipped canonical facts: **0**
- Source entities: **10**
- Fact/entity associations: **50**
- SQLite integrity check: **ok**
- Source search latency: **median 2.829 ms across 8 probes**

| Memanto type | Count |
|---|---:|
| `fact` | 60 |
| `preference` | 12 |

## Structural fidelity

- Result: **PASS**
- Field assertions checked: **1008**
- Mismatches: **0**
- Holo memories found in bundle: **72**

## Physical / logical accounting

| Metric | Bytes / count |
|---|---:|
| Source SQLite file | 110592 bytes |
| Canonical fact content | 6497 bytes |
| Canonical tag strings | 2060 bytes |
| Holo HRR fact vectors | 0 bytes |
| Holo memory-bank vectors | 0 bytes |
| Exported OKF bundle | 67703 bytes |
| OKF files | 76 |
| Approx. canonical-content tokens (`bytes / 4`) | 1625 |

**Accounting note:** the direct `memanto migrate okf` path does not generate the provider-style Memanto savings report. These numbers are therefore a Holo-specific accounting report. Reductions in SQLite indexes or vector bytes are **not** described as token savings. The token figure above is only a labeled rough estimate for canonical UTF-8 fact content.

## Derived-data policy

- FTS present in source: `True` → **rebuild**
- Facts carrying HRR vectors: `0` → **rebuild**
- Memory banks: `0` → **rebuild**
- Query-time relatedness / contradiction behavior → **validate, do not fabricate as stored history**

## Integrity identifiers

- Source SQLite SHA-256: `1e9b0fe92496ef5efa1d1c7f9b92c8d5a14ca430bae389c83e3c21a5bfb46348`
- Bundle manifest SHA-256: `a24cff32504576fd829409380952831557b76e7af524b5bc9c5503ff5ff6d2cd`

## Bounded claim

Hermes Holographic canonical facts, trust, timestamps, tags, and entity associations are exported into human-readable OKF and independently checked against the SQLite source. Derived retrieval structures are explicitly rebuilt rather than misrepresented as canonical portable knowledge.
