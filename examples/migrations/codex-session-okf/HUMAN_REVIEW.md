# Human product review

Date: 2026-07-30

The contributor reviewed the adapter's export boundary and chose the strict
mode: export only user and assistant text. System and developer instructions,
reasoning, tool calls, function payloads, and tool results remain excluded.

Product rationale:

> The migration goal is to preserve reusable conversational knowledge. Tool
> execution details are not long-term memory and would increase privacy risk.

This decision confirms the existing deny-by-default design. No tool-call
summary support should be added for this submission.
