---
type: decision
title: 'Lead Cedar Hobby: cold (25)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:cold
timestamp: '2026-07-30T09:00:59.309Z'
resource: http://localhost:5679/workflow/nuMIHADKIMhTbCFc/executions/6
x_memanto:
  id: n8n-f9e93c7aea9432de737301f5
  confidence: 1.0
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision

- **Company**: Cedar Hobby
- **Use case**: Send a monthly newsletter
- **Qualification score**: 25
- **Route**: cold
- **Reasons**: `["budget provided","company size provided","urgency: researching","business email","complete core profile"]`
- **Next action**: Add to educational nurture; no sales notification.
- **Processed at**: 2026-07-30T09:00:59.307Z
- **Follow up at**: 2026-07-31T09:00:59.307Z
- **Idempotency key**: a09c0bc9

## n8n provenance

- **Workflow**: LeadOps — Intake, Scoring & Follow-up (`nuMIHADKIMhTbCFc`)
- **Execution**: `6`
- **Node**: Normalize, Score & Route
- **Position**: run 0, output 0, item 0
- **Execution status**: success
