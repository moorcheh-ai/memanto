# multi_agent_codebase_handoff_v1

A deterministic benchmark for shared memory in multi-agent coding workflows. Facts mutate across planning, implementation, review, QA, docs, and release handoff turns.

## Summary

| Backend | Accuracy | Cross-Agent Accuracy | Ingested Tokens | Retrieved Tokens | p95 Latency (s) | Stale Conflict Rate | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shared_active_digest | 100.0% | 100.0% | 252 | 291 | 0.000276 | 0.0% | 1.00 |
| shared_append_log | 80.0% | 80.0% | 252 | 1704 | 0.000291 | 50.0% | 0.25 |
| per_agent_append_log | 0.0% | 0.0% | 252 | 590 | 0.000038 | 10.0% | 0.03 |

## Per-Question Accuracy

| Question | Backend | Correct | Retrieved Tokens | Retrieved Keys |
| --- | --- | ---: | ---: | --- |
| q1 | shared_active_digest | yes | 31 | imports.api.contract |
| q2 | shared_active_digest | yes | 23 | imports.auth.scope |
| q3 | shared_active_digest | yes | 24 | feature.flag |
| q4 | shared_active_digest | yes | 33 | test.blocker |
| q5 | shared_active_digest | yes | 19 | database.migration |
| q6 | shared_active_digest | yes | 35 | docs.warning |
| q7 | shared_active_digest | yes | 31 | rollout.region |
| q8 | shared_active_digest | yes | 34 | owner.oncall |
| q9 | shared_active_digest | yes | 27 | rollback.plan |
| q10 | shared_active_digest | yes | 34 | customer.message |
| q1 | shared_append_log | yes | 161 | imports.api.contract, imports.api.contract, imports.auth.scope, feature.flag, imports.auth.scope, customer.message |
| q2 | shared_append_log | no | 158 | imports.auth.scope, imports.auth.scope, feature.flag, test.blocker, customer.message, owner.oncall |
| q3 | shared_append_log | no | 168 | feature.flag, feature.flag, rollback.plan, test.blocker, docs.warning, customer.message |
| q4 | shared_append_log | yes | 178 | test.blocker, test.blocker, feature.flag, rollout.region, owner.oncall, rollout.region |
| q5 | shared_append_log | yes | 177 | database.migration, test.blocker, test.blocker, owner.oncall, customer.message, rollback.plan |
| q6 | shared_append_log | yes | 192 | docs.warning, imports.api.contract, customer.message, owner.oncall, rollback.plan, rollout.region |
| q7 | shared_append_log | yes | 156 | rollout.region, feature.flag, rollout.region, imports.auth.scope, test.blocker, imports.auth.scope |
| q8 | shared_append_log | yes | 179 | owner.oncall, test.blocker, feature.flag, rollout.region, customer.message, rollout.region |
| q9 | shared_append_log | yes | 159 | feature.flag, rollback.plan, test.blocker, feature.flag, rollout.region, customer.message |
| q10 | shared_append_log | yes | 176 | customer.message, feature.flag, rollout.region, rollout.region, owner.oncall, rollback.plan |
| q1 | per_agent_append_log | no | 23 | imports.auth.scope |
| q2 | per_agent_append_log | no | 56 | imports.auth.scope, feature.flag, database.migration |
| q3 | per_agent_append_log | no | 69 | docs.warning, customer.message |
| q4 | per_agent_append_log | no | 84 | rollout.region, rollout.region, rollback.plan |
| q5 | per_agent_append_log | no | 63 | test.blocker, test.blocker |
| q6 | per_agent_append_log | no | 56 | database.migration, feature.flag, imports.auth.scope |
| q7 | per_agent_append_log | no | 23 | imports.auth.scope |
| q8 | per_agent_append_log | no | 69 | customer.message, docs.warning |
| q9 | per_agent_append_log | no | 63 | test.blocker, test.blocker |
| q10 | per_agent_append_log | no | 84 | rollout.region, rollout.region, rollback.plan |

## Controls

- Backend LLM: none; offline golden dataset matching
- Judge: exact key/value matching with stale conflict detection
- Prompt/system instructions: none
- Host: Windows-11-10.0.26200-SP0 / CPython
