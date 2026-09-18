---
type: "error"
title: "Error from ledger-portability-final"
description: "Extracted from a goose assistant message."
resource: "goose-session-export.json#1/message-2"
tags: ["goose", "transcript", "assistant", "error"]
timestamp: "2026-09-08T04:14:54+00:00"
x_memanto:
  source: "goose-sessions"
  source_ref: "goose-session-export.json#1/message-2"
  confidence: 0.74
  provenance: imported
---

Updated only `reconciliation_key` in `ledger.py` to return a deterministic SHA-256 hex digest based on `merchant_id` and `external_id`. Test results after the change: - `test_reconciliation_key_is_stable_sha256` — passed - `test_audit_line_does_not_store_customer_email` — failed Remaining failure: `audit_line` still includes the full email address. As requested, `audit_line` was left unchanged.
