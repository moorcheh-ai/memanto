---
type: decision
title: 'Lead Beacon Studio: warm (65)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:warm
timestamp: '2026-07-30T09:00:59.268Z'
resource: http://localhost:5679/workflow/nuMIHADKIMhTbCFc/executions/5
x_memanto:
  id: n8n-057bccc8069d70a10f7508f0
  confidence: 1.0
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision

- **Company**: Beacon Studio
- **Use case**: Reduce manual lead qualification
- **Qualification score**: 65
- **Route**: warm
- **Reasons**: `["budget ≥ $2k","company size ≥ 10","urgency: this_quarter","strong automation intent","business email","complete core profile"]`
- **Next action**: Send a relevant case study and ask one qualifying question.
- **Processed at**: 2026-07-30T09:00:59.266Z
- **Follow up at**: 2026-07-30T13:00:59.266Z
- **Idempotency key**: 7204bd61

## n8n provenance

- **Workflow**: LeadOps — Intake, Scoring & Follow-up (`nuMIHADKIMhTbCFc`)
- **Execution**: `5`
- **Node**: Normalize, Score & Route
- **Position**: run 0, output 0, item 0
- **Execution status**: success
