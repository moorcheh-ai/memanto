# Demo Transcript

This transcript shows the expected behavior when running the example in preview
mode. With `MOORCHEH_API_KEY` configured, the same graph stores and recalls the
memories through Memanto instead of the local preview file.

```text
$ python run_demo.py --mode seed --preview
Using local preview memory store: .langgraph_memanto_preview.json

Customer: ACME
Message: ACME prefers hosted deployments that are SOC 2 compliant. They want async email updates after each deployment step.

Recalled memories:
- No previous memories found.

Graph classification:
- intent: capture_customer_context
- should_store_memory: yes

Stored memory:
- ACME deployment preference

Assistant response:
I saved ACME's deployment preference and communication requirement so future
support turns can use it without asking again.

$ python run_demo.py --mode follow-up --preview
Using local preview memory store: .langgraph_memanto_preview.json

Customer: ACME
Message: ACME is asking which deployment path we recommend before launch.

Recalled memories:
- ACME deployment preference: ACME prefers hosted deployments that are SOC 2 compliant. They want async email updates after each deployment step.

Graph classification:
- intent: answer_with_memory
- should_store_memory: no

Assistant response:
Recommend the hosted deployment path for ACME, emphasize SOC 2 compliance, and
async email updates after each deployment step.
```
