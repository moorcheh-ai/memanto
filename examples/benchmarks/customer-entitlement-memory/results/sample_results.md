# Customer Entitlement Memory Benchmark

Fixture version: `2026-06-22`
Account: `Acme Robotics`

## Summary

| Backend | Accuracy | Passed | Stale conflict rate | Avg retrieved tokens | Avg scanned tokens | p95 latency proxy (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active_entitlement_digest | 100% | 10/10 | 0% | 36.50 | 24.80 | 4.175 |
| append_only_log | 50% | 5/10 | 50% | 49.80 | 480.00 | 19.820 |
| recent_window_log | 30% | 3/10 | 20% | 31.80 | 208.00 | 10.300 |

## Interpretation

The active entitlement digest keeps one current fact per key and scope, so it preserves long-lived facts like SSO and SLA while suppressing stale billing, escalation, beta, and compliance states.

The append-only log retains full history but surfaces stale and private facts. The recent-window log avoids some stale history, but it forgets older facts that are still operationally current.

## Per-query Failures

### active_entitlement_digest

No failures.

### append_only_log

- `q-invoice-po`: forbidden=['PO-4487'], evidence=['evt-2026-06-12-billing-compliance'], answer=Which purchase order should be used on the next invoice? invoice_po[billing] = PO-4487 (evidence: evt-2026-01-05-kickoff, 2026-01-05); invoice_po[billing] = PO-7721 (evidence: evt-2026-06-12-billing-compliance, 2026-06-12)
- `q-audit-beta`: forbidden=['enabled until 2026-05-30'], evidence=['evt-2026-05-30-beta-extension'], answer=Is the audit export beta still enabled, and until when? audit_export_beta[feature_flag] = enabled until 2026-05-30 (evidence: evt-2026-04-15-beta, 2026-04-15); audit_export_beta[feature_flag] = enabled until 2026-06-30 (evidence: evt-2026-05-30-beta-extension, 2026-05-30)
- `q-support-lead`: forbidden=['Nora Li'], evidence=['evt-2026-05-30-beta-extension'], answer=Who is the current support lead? support_lead[people] = Nora Li (evidence: evt-2026-04-15-beta, 2026-04-15); support_lead[people] = Iris Chen (evidence: evt-2026-05-30-beta-extension, 2026-05-30)
- `q-escalation`: forbidden=['#acme-old', 'Slack channel'], evidence=['evt-2026-03-02-escalation'], answer=Where should urgent support escalations go now? escalation_route[support] = Slack channel #acme-old (evidence: evt-2026-01-05-kickoff, 2026-01-05); escalation_route[support] = PagerDuty service acme-primary (evidence: evt-2026-03-02-escalation, 2026-03-02)
- `q-hipaa`: forbidden=['pending'], evidence=['evt-2026-06-12-billing-compliance'], answer=What is the current HIPAA addendum status? hipaa[compliance] = HIPAA addendum pending (evidence: evt-2026-02-11-enterprise, 2026-02-11); hipaa[compliance] = HIPAA addendum signed (evidence: evt-2026-06-12-billing-compliance, 2026-06-12)

### recent_window_log

- `q-production-region`: forbidden=[], evidence=[], answer=What production data residency should support quote for Acme Robotics? No publishable memory found.
- `q-audit-beta`: forbidden=['enabled until 2026-05-30'], evidence=['evt-2026-05-30-beta-extension'], answer=Is the audit export beta still enabled, and until when? audit_export_beta[feature_flag] = enabled until 2026-05-30 (evidence: evt-2026-04-15-beta, 2026-04-15); audit_export_beta[feature_flag] = enabled until 2026-06-30 (evidence: evt-2026-05-30-beta-extension, 2026-05-30)
- `q-support-lead`: forbidden=['Nora Li'], evidence=['evt-2026-05-30-beta-extension'], answer=Who is the current support lead? support_lead[people] = Nora Li (evidence: evt-2026-04-15-beta, 2026-04-15); support_lead[people] = Iris Chen (evidence: evt-2026-05-30-beta-extension, 2026-05-30)
- `q-escalation`: forbidden=[], evidence=[], answer=Where should urgent support escalations go now? No publishable memory found.
- `q-sso`: forbidden=[], evidence=[], answer=Which SSO provider is configured? No publishable memory found.
- `q-private-budget`: forbidden=[], evidence=[], answer=What renewal budget details should a support answer include? No publishable memory found.
- `q-p2-sla`: forbidden=[], evidence=[], answer=What is the P2 support SLA? No publishable memory found.
