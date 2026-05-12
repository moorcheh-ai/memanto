# Terminal Proof

This transcript can be reproduced with the local backend:

```bash
cd examples/langgraph-memanto
python run_full_demo.py --backend local --reset-local
```

Expected output:

```text
=== Run 1: support agent stores durable customer context ===
Session: session-1-store
Customer: ada-lovelace
Action: ask_clarifying_question
Stored memories: 3
Recalled memories: 0

Stored:
- preference: Ada prefers concise support replies [local-...]
- preference: Ada wants email delivery [local-...]
- fact: Ada is on the Pro plan [local-...]

Reply:
I can help set that up. Which email address should receive the analytics export?

=== Run 2: new support session recalls prior context ===
Session: session-2-recall
Customer: ada-lovelace
Action: draft_concise_email_first_reply
Stored memories: 0
Recalled memories: 3

Recalled:
- fact: Ada is on the Pro plan (score=...)
- preference: Ada prefers concise support replies (score=...)
- preference: Ada wants email delivery (score=...)

Reply:
Hi Ada,

Yes. Since you are on the Pro plan, I can keep this concise and set the analytics export to be delivered by email.

I used these recalled memories:
- Ada is on the Pro plan: Customer ada-lovelace is on the Pro plan and can use scheduled analytics exports.
- Ada prefers concise support replies: Customer ada-lovelace prefers concise, direct support replies without marketing language.
- Ada wants email delivery: Customer ada-lovelace prefers analytics exports and follow-up instructions delivered by email.

Next step: confirm the destination email address and export cadence.
```
