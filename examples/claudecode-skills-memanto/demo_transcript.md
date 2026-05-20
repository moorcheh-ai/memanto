# Demo Transcript

Skill: `/grill-with-docs`
Task: Plan invoice import architecture

Decision: Use a streaming parser for invoice CSV imports because customers can
upload exports with hundreds of thousands of rows.

Decision: Keep raw import rows in storage for auditability before converting
them into normalized invoice records.

Preference: The codebase prefers explicit domain services over framework magic
for billing workflows.

Constraint: Avoid adding a second queue system; reuse the existing background
job runner unless load testing proves it cannot keep up.

Artifact: The parser contract should return accepted rows, rejected rows, and a
stable import batch id for reconciliation.
