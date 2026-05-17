# Demo Transcript

This is the expected output path for the credential-free demo.

```text
$ python run_demo.py --backend local --reset-local

LangGraph + Memanto cross-session recall demo
Backend: local
Memanto agent id: langgraph-recruiting-memory

SESSION 1 - yesterday, thread_id=intake-2026-05-17
User: Record this from yesterday: Candidate Maya Chen is interviewing for Staff
  AI Platform. She prefers concise technical deep-dives, is available after
  14:00 UTC, and we promised a take-home by Friday.
Agent: I captured the candidate details and will store them in Memanto so a
  later LangGraph thread can recall them without receiving this message again.
Stored memories: 4

SESSION 2 - today, thread_id=briefing-2026-05-18
User: I have a new LangGraph thread with no notes in state. Prepare my reminder
  for today's Maya interview.
Agent: This is a fresh LangGraph thread, but Memanto recalled yesterday's
  durable context:
  - Maya Chen interview style: Maya Chen prefers concise technical deep-dives
  over broad introductory prompts.
  - Maya Chen role: Yesterday's intake said Maya Chen is interviewing for the
  Staff AI Platform role.
  - Maya Chen take-home commitment: The team promised Maya Chen a take-home
  exercise by Friday.
  - Maya Chen availability: Maya Chen is available after 14:00 UTC for
  interviews.

  Interview prep: start with a concise systems question, schedule after 14:00
  UTC, and send the promised take-home by Friday.
Recalled memories: 4

Proof
- Different LangGraph thread ids: intake-2026-05-17 != briefing-2026-05-18
- Session 2 did not include Maya's role, style, time, or commitment.
- Those details came from the long-term memory backend.
```
