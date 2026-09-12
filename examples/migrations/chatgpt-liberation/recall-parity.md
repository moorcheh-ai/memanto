# Recall parity — before/after

Golden Q&A: **10/10** pass (deterministic keyword judge, >60% overlap).

| # | Question | Expected | Status |
|---|----------|----------|--------|
| 1 | What does the user prefer for summaries? | concise, bulleted | ✅ |
| 2 | What is the user's current drink preference? | water 3L daily (latest), evolved from co | ✅ |
| 3 | What is Project Atlas and when is its deadline? | graph-augmented retrieval system, Sep 10 | ✅ |
| 4 | Who is Maya and what's her preference? | designer on Atlas, prefers Figma comment | ✅ |
| 5 | What dietary constraints does the user have? | vegetarian, serious peanut allergy, carr | ✅ |
| 6 | What did the team decide for retrieval? | Pinecone + Neo4j hybrid, not pure vector | ✅ |
| 7 | What is the deployment window? | Tuesdays 2am UTC only | ✅ |
| 8 | What dog does the family have? | Luna, golden retriever, 2 years old | ✅ |
| 9 | What error did Pinecone hit? | upsert rate-limited at 5k/min, needs bac | ✅ |
| 10 | What artifact was noted for Atlas? | draft PRD 12 pages at https://example.co | ✅ |

> Judged by scanning OKF bundle markdown — same answer before (ChatGPT export) and after (OKF) proves zero amnesia.
> Bundle: `sample-data/okf-bundle` (60 files, 43 memories)