# Live Moorcheh verification report

Verified on 2026-08-06 UTC against the `crewai-okf-verified` Memanto agent.
No API keys, account identifiers, or customer data are included in these
artifacts.

## Import

The checked-in OKF bundle was imported with Memanto's shipped CLI:

```console
memanto migrate okf artifacts/verified/okf-bundle --agent crewai-okf-verified
```

- OKF nodes: 8
- mapped: 8
- skipped: 0
- imported: 8
- failed: 0
- batches: 1
- types: 2 decisions and one each of error, goal, instruction, learning,
  preference, and relationship

## Recall after migration

The exact six golden questions from `source-run.json` were asked against the
live agent with `memanto recall <question> --limit 3`.

| # | Expected memory | Source recall rank | Live Moorcheh rank |
|---:|---|---:|---:|
| 1 | Current PostgreSQL decision | 1 | 1 |
| 2 | Analytics privacy instruction | 1 | 1 |
| 3 | AUR-218 root cause | 1 | 1 |
| 4 | AUR-218 remediation | 2 | 1 |
| 5 | Aurora pilot goal | 1 | 1 |
| 6 | Aurora ownership relationship | 2 | 1 |

Result: **6/6 expected memories in source top 3 and 6/6 live expected memories
at rank 1.** The complete machine-readable result is in
`live-recall-report.json`.

## Export back out

The live agent was exported with Memanto's OKF exporter:

```console
memanto memory export --okf --split type --agent crewai-okf-verified
```

Memanto reported 8 exported memories. Loading the exported bundle again with
Memanto's own `load_okf_bundle` and `map_okf` returned 8 loaded and 8 mapped
memories with the same type distribution. The exported bundle is checked in at
`artifacts/verified/live-export`.
