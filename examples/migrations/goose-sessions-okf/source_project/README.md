# Ledger portability demo

This small project gives Goose a real, testable task for the Memanto migration
showcase. The session should remember three project rules:

- reconciliation keys must be deterministic across machines;
- audit output must not contain a customer's full email address;
- `python -m unittest -v` is the required check before a change is considered done.

The project deliberately starts with two failing tests. Goose fixes them during
the recorded session, and the resulting local session database becomes the
input to the migration adapter.
