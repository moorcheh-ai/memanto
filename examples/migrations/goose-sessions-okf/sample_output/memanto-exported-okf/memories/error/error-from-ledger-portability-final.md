---
type: error
title: Error from ledger-portability-final
description: Extracted from a goose assistant message.
tags:
- goose
- transcript
- assistant
- error
generated:
  by: process:goose-sessions
  at: '2026-09-08T04:14:54+00:00'
resource: goose-session-export.json#1/message-2
x_memanto:
  id: ebb5b6e9-437d-420c-9974-62028684ef39
  confidence: 0.74
  provenance: imported
  source: goose-sessions
  status: active
  updated_at: '2026-09-08T04:36:59.245021+00:00'
  type: error
---

Extracted from a goose assistant message.

Updated only `reconciliation_key` in `ledger.py` to return a deterministic SHA-256 hex digest based on `merchant_id` and `external_id`. Test results after the change: - `test_reconciliation_key_is_stable_sha256` — passed - `test_audit_line_does_not_store_customer_email` — failed Remaining failure: `audit_line` still includes the full email address. As requested, `audit_line` was left unchanged.

---
[Supporting data]
- OKF source: memories\error\error-from-ledger-portability-final.md
- OKF resource: goose-session-export.json#1/message-2
