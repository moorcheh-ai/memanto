# Atlas Relay

Atlas Relay is a small command-line service that accepts deployment jobs and
dispatches them to workers.

## Current Baseline

- Runtime: Python 3.10 or newer
- Prototype storage: SQLite
- Timestamps: mixed local time and UTC
- Logs: human-readable text

## Open Design Question

The prototype is moving from one local worker to several shared workers. The
team needs to settle storage, timestamp, and logging conventions before
implementation starts.
