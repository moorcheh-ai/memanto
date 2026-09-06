---
type: decision
title: 'Lead Beacon Studio: warm (65)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:warm
timestamp: '2026-07-30T09:00:59.268000+00:00'
resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/5
x_memanto:
  id: 361c0046-1c6d-4aa9-a950-e39df10d46a7
  confidence: 1
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision: Beacon Studio

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

---
[Supporting data]
- OKF source: memories/decision/lead-beacon-studio-warm-65.md
- OKF resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/5

<!-- okf-entry -->
---
type: decision
title: 'Lead Atlas Fleet: hot (100)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:hot
timestamp: '2026-07-30T09:00:59.222000+00:00'
resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/4
x_memanto:
  id: 1f4ac259-97e7-439c-ac86-23484dba0f4f
  confidence: 1
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision: Atlas Fleet

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

---
[Supporting data]
- OKF source: memories/decision/lead-atlas-fleet-hot-100.md
- OKF resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/4

<!-- okf-entry -->
---
type: decision
title: 'Lead Cedar Hobby: cold (25)'
description: Lead Routing Decision
tags:
- n8n
- leadops
- route:cold
timestamp: '2026-07-30T09:00:59.309000+00:00'
resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/6
x_memanto:
  id: 964af21d-d989-4240-96a4-e3a2f5c1a390
  confidence: 1
  provenance: n8n_execution
  source: tool
  status: active
  type: decision
---

# Lead Routing Decision: Cedar Hobby

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

---
[Supporting data]
- OKF source: memories/decision/lead-cedar-hobby-cold-25.md
- OKF resource: n8n://workflow/nuMIHADKIMhTbCFc/executions/6
