# Session Summary for crewai-okf-verified
**Session ID:** `unknown`

---

## [2026-08-06 00:42:46] [DECISION] Original SQLite decision
- **Memory ID**: `c438c5ce-dc4c-4377-8310-29f0de98b4b6`
- **Confidence**: `0.45`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `decision`, `database`, `superseded`, `scope-decisions`, `scope-platform`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> The Aurora pilot originally selected SQLite for the order ledger because the prototype ran on one node.
>
> ---
> [Supporting data]
> - OKF source: memories/decision/original-sqlite-decision-43c69696-2be5-40f3-b.md
> - OKF resource: crewai://unified-memory/43c69696-2be5-40f3-b92b-77c3bb48ef6c
> - OKF crewai: schema=unified-memory-lancedb; id=43c69696-2be5-40f3-b92b-77c3bb48ef6c; scope=/decisions/platform; categories=['decision', 'database', 'superseded']; metadata={'title': 'Original SQLite decision', ...
> - OKF source_record_sha256: 7d1b184b6be9e0adbdea4ec620295d061441055e75f9d801be64063f71f70a0a
> - OKF redactions: 0

---

## [2026-08-06 00:42:47] [DECISION] PostgreSQL 16 is the current ledger decision
- **Memory ID**: `5b1d8b23-fcca-48f0-9a61-04e95cdf8312`
- **Confidence**: `0.96`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `decision`, `database`, `current`, `scope-decisions`, `scope-platform`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> The Aurora order ledger must use PostgreSQL 16, replacing SQLite, because concurrent writers and point-in-time recovery are required.
>
> ---
> [Supporting data]
> - OKF source: memories/decision/postgresql-16-is-the-current-ledger-decision-84b237f2-3188-4230-9.md
> - OKF resource: crewai://unified-memory/84b237f2-3188-4230-9776-67ec3c5e4db6
> - OKF crewai: schema=unified-memory-lancedb; id=84b237f2-3188-4230-9776-67ec3c5e4db6; scope=/decisions/platform; categories=['decision', 'database', 'current']; metadata={'title': 'PostgreSQL 16 is the current l...
> - OKF source_record_sha256: 504313e902204b263dc907c8b5b794ca82902f0713ba17bce2c7bf678378a597
> - OKF redactions: 0

---

## [2026-08-06 00:42:47] [ERROR] AUR-218 duplicate invoice root cause
- **Memory ID**: `95866e88-bd85-4961-b4ec-a7660d82e434`
- **Confidence**: `0.94`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `error`, `incident`, `billing`, `scope-errors`, `scope-billing`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> Invoice retry incident AUR-218 duplicated three invoices because the worker retried after a timeout without an idempotency key.
>
> ---
> [Supporting data]
> - OKF source: memories/error/aur-218-duplicate-invoice-root-cause-bc26de54-75d1-47bd-9.md
> - OKF resource: crewai://unified-memory/bc26de54-75d1-47bd-938b-d185650124b8
> - OKF crewai: schema=unified-memory-lancedb; id=bc26de54-75d1-47bd-938b-d185650124b8; scope=/errors/billing; categories=['error', 'incident', 'billing']; metadata={'title': 'AUR-218 duplicate invoice root cause'...
> - OKF source_record_sha256: a7be2788257ff3728f8e69e30cb9f4eaa0fc4bc349c9e0eae340c856fdbe68e7
> - OKF redactions: 0

---

## [2026-08-06 00:42:48] [GOAL] Aurora EU pilot exit goal
- **Memory ID**: `ddf99c26-768d-461a-8154-024b33de33e1`
- **Confidence**: `0.98`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `goal`, `deadline`, `slo`, `scope-goals`, `scope-delivery`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> Ship the Aurora EU pilot by 2026-08-28 with checkout p95 below 350 milliseconds and zero unresolved severity-one defects.
>
> ---
> [Supporting data]
> - OKF source: memories/goal/aurora-eu-pilot-exit-goal-87b70ac8-30d2-41d0-8.md
> - OKF resource: crewai://unified-memory/87b70ac8-30d2-41d0-8453-b5d2502383b0
> - OKF crewai: schema=unified-memory-lancedb; id=87b70ac8-30d2-41d0-8453-b5d2502383b0; scope=/goals/delivery; categories=['goal', 'deadline', 'slo']; metadata={'title': 'Aurora EU pilot exit goal', 'memory_type':...
> - OKF source_record_sha256: 65b1e398007820d27dc60fbbfdf45d3180c00ab897f99154d1e300c76e053847
> - OKF redactions: 0

---

## [2026-08-06 00:42:47] [INSTRUCTION] Analytics email privacy rule
- **Memory ID**: `57b58174-d88e-4f9d-9127-3907974d4acb`
- **Confidence**: `1.0`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `instruction`, `privacy`, `pii`, `scope-instructions`, `scope-security`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> Never persist raw customer email addresses in analytics events; store a salted irreversible hash and keep the salt in the secret manager.
>
> ---
> [Supporting data]
> - OKF source: memories/instruction/analytics-email-privacy-rule-85450f4d-2eb3-4f62-b.md
> - OKF resource: crewai://unified-memory/85450f4d-2eb3-4f62-bf51-2f1d0bc71c99
> - OKF crewai: schema=unified-memory-lancedb; id=85450f4d-2eb3-4f62-bf51-2f1d0bc71c99; scope=/instructions/security; categories=['instruction', 'privacy', 'pii']; metadata={'title': 'Analytics email privacy rule'...
> - OKF source_record_sha256: 59575c7259f2016ad15e8ce6b1742a5a8e0403277e29f50b51a3383cc6d5dbfb
> - OKF redactions: 0

---

## [2026-08-06 00:42:47] [LEARNING] AUR-218 idempotency remediation
- **Memory ID**: `d1d626f9-dfce-495b-a6ef-6233acf11184`
- **Confidence**: `0.93`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `learning`, `remediation`, `billing`, `scope-learnings`, `scope-billing`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> All invoice creation calls now require the event UUID as an idempotency key, and the database enforces a unique constraint on it.
>
> ---
> [Supporting data]
> - OKF source: memories/learning/aur-218-idempotency-remediation-b380bc30-d008-4fee-b.md
> - OKF resource: crewai://unified-memory/b380bc30-d008-4fee-b554-8e390ec2a3ac
> - OKF crewai: schema=unified-memory-lancedb; id=b380bc30-d008-4fee-b554-8e390ec2a3ac; scope=/learnings/billing; categories=['learning', 'remediation', 'billing']; metadata={'title': 'AUR-218 idempotency remediat...
> - OKF source_record_sha256: 57a64e347612d1b04d42efd34dc226b31ba573353404ed2cabc0d7c75236d6d5
> - OKF redactions: 0

---

## [2026-08-06 00:42:47] [PREFERENCE] Sponsor reporting preference
- **Memory ID**: `5b60578d-ac1c-4c16-8683-c7612374a2c3`
- **Confidence**: `0.84`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `preference`, `reporting`, `stakeholder`, `scope-preferences`, `scope-stakeholders`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> The pilot sponsor prefers concise evidence tables with raw numbers and confidence bounds; avoid hype and decorative dashboards.
>
> ---
> [Supporting data]
> - OKF source: memories/preference/sponsor-reporting-preference-e7017675-11b8-49a7-9.md
> - OKF resource: crewai://unified-memory/e7017675-11b8-49a7-96ce-f570d402f979
> - OKF crewai: schema=unified-memory-lancedb; id=e7017675-11b8-49a7-96ce-f570d402f979; scope=/preferences/stakeholders; categories=['preference', 'reporting', 'stakeholder']; metadata={'title': 'Sponsor reporting...
> - OKF source_record_sha256: 68520fac7d1420535b96784b1689a236613a677dabaabf4f1634d6258a7f6c56
> - OKF redactions: 0

---

## [2026-08-06 00:42:48] [RELATIONSHIP] Aurora checkout ownership
- **Memory ID**: `d0db5ab8-477c-487f-9878-7c1b534cd888`
- **Confidence**: `0.82`
- **Status**: `active`
- **Source**: `crewai`
- **Provenance**: `imported`
- **Tags**: `crewai`, `relationship`, `ownership`, `approval`, `scope-relationships`, `scope-aurora`
- **Content**:
> Migrated from CrewAI unified memory (LanceDB).
>
> Maya owns the Aurora checkout workstream, and Rafael is the security approver required before the EU pilot can launch.
>
> ---
> [Supporting data]
> - OKF source: memories/relationship/aurora-checkout-ownership-9f451abf-0167-42e6-9.md
> - OKF resource: crewai://unified-memory/9f451abf-0167-42e6-9d16-8dcd4317ce0f
> - OKF crewai: schema=unified-memory-lancedb; id=9f451abf-0167-42e6-9d16-8dcd4317ce0f; scope=/relationships/aurora; categories=['relationship', 'ownership', 'approval']; metadata={'title': 'Aurora checkout owners...
> - OKF source_record_sha256: 63ea2ee2cce8f21120525b7fe12b19e784f27a3ed45f68cea1fcc9ccd7930187
> - OKF redactions: 0

---
