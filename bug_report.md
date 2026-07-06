# Memanto Bug Report: Timeline Amnesia via Timestamp Collision

## Summary
A critical logic flaw in Memanto's memory retrieval causes timeline amnesia when two events are recorded with the same timestamp (down to millisecond precision). The system fails to maintain temporal ordering, leading to incorrect recall and potential context corruption.

## Steps to Reproduce
1. Initialize Memanto agent with `moorcheh.ai` backend.
2. Record two consecutive events with identical timestamps (e.g., by calling `memorize` rapidly in a loop).
3. Query for the most recent event.
4. Observe that the order is arbitrary and often the wrong event is returned.

## Impact
- Memory integrity compromised.
- Agent may hallucinate timelines.
- Critical for applications requiring strict temporal reasoning.

## Suggested Fix
Add a monotonic counter or nanosecond precision to timestamps to ensure unique ordering.

## Proof of Concept
See `poc_timeline_amnesia.py` for a reproducible example.