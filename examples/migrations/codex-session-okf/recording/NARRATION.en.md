# English narration

## Scene 1

Agent memory is valuable, but it should not be trapped inside one product.
This demo starts with a privacy-safe subset from a genuine Codex session.
The adapter accepts reusable user and assistant messages, while rejecting
system prompts, reasoning, tool calls, credentials, and transport metadata.

## Scene 2

The converter turns the session into Open Knowledge Format. Each memory is
plain Markdown with readable metadata, so a person can inspect it, version it
with Git, and carry it to another system.

## Scene 3

The automated privacy tests pass. The same three golden questions are present
in both the source archive and the generated OKF bundle, giving exact recall
parity before migration.

## Scene 4

Memanto's official importer loads all four OKF nodes and maps all four into
context memories. The dry run writes nothing and confirms the mapping first.

## Scene 5

Now the same bundle is imported into a new, isolated Memanto agent. Four
memories are imported with zero failures.

## Scene 6

The migrated agent still retrieves the expected date, the Python project
Memanto, and the TypeScript project bounty-radar. The expected answer ranks
first for every golden question.

## Scene 7

Finally, all four memories are exported from Memanto back into readable OKF.
The freedom loop is complete: Codex session, portable OKF, Memanto memory, and
portable OKF again. The agent keeps its knowledge, and the user keeps ownership.
