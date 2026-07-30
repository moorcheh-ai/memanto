# Recorded Memanto dry run

This is the recorded result of running Memanto's shipped OKF importer against
the committed bundle:

```text
Command:
memanto migrate okf examples/migrations/n8n_executions/sample-okf --dry-run

OKF nodes: 3
Mapped memories: 3 (skipped 0)
Type breakdown: decision: 3
Dry run: no writes performed
```

The mapped rows emitted by that command are committed as
`memanto-dry-run-preview.json`.

Latest recorded run ID: `20260730_095436` (under Memanto's local OKF
migration run directory).

The mapped preview SHA-256 is
`d6f17a95582a6438b931183332d2658333ff985a0402f9b968230014e4dfa182`.

## Source evidence

- Source tool: n8n `2.32.6`
- Workflow: `LeadOps — Intake, Scoring & Follow-up`
- Workflow ID: `nuMIHADKIMhTbCFc`
- Execution IDs: `4`, `5`, `6`
- Execution status: `success` for all three
- Export endpoint: `GET /api/v1/executions?includeData=true`
- Source export SHA-256:
  `a927c54768ce3aa6eeb404f459072938dcb959b568c40d32be8871cfca02b346`

## Fidelity evidence

- Source records: `3`
- OKF memories: `3`
- Memanto-mapped rows: `3`
- Stable source-derived IDs preserved: `true`
- Golden questions: `3/3`
- Recall parity: `1.0`
