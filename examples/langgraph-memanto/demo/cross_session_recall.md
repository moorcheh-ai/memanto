# Cross-Session Recall Demo Transcript

Command:

```bash
python demo_cross_session.py
```

Output:

```text
Session 1 wrote memory:
{'memory_id': 'local-...', 'type': 'preference', 'title': 'Dashboard delivery preferences', 'content': 'dashboard walkthroughs should use dark mode; reports should be exported as CSV', 'confidence': 0.95, 'tags': ['support', 'cross-session'], 'created_at': '...'}

Session 2 recalled memories:
- dashboard walkthroughs should use dark mode; reports should be exported as CSV

Session 2 answer:
For avery, use dark mode and export reports as CSV. Those settings came from Memanto recall, not the current graph state.

CROSS-SESSION RECALL VERIFIED
```
