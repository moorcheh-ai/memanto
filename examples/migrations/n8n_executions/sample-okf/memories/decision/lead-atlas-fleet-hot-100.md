---
type: decision
title: 'Lead Atlas Fleet: hot (100)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:hot
timestamp: '2026-07-30T09:00:59.222Z'
resource: http://localhost:5679/workflow/nuMIHADKIMhTbCFc/executions/4
x_memanto:
  id: n8n-4cf4dea1abe0f6a3c4adff37
  confidence: 1.0
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision

- **Company**: Atlas Fleet
- **Use case**: Automate CRM lead routing and manual follow-up workflows
- **Qualification score**: 100
- **Route**: hot
- **Reasons**: `["budget ≥ $10k","company size ≥ 50","urgency: immediate","strong automation intent","business email","complete core profile"]`
- **Next action**: Offer a priority discovery call.
- **Processed at**: 2026-07-30T09:00:59.219Z
- **Follow up at**: 2026-07-30T09:15:59.219Z
- **Idempotency key**: 5da0a075

## n8n provenance

- **Workflow**: LeadOps — Intake, Scoring & Follow-up (`nuMIHADKIMhTbCFc`)
- **Execution**: `4`
- **Node**: Normalize, Score & Route
- **Position**: run 0, output 0, item 0
- **Execution status**: success
