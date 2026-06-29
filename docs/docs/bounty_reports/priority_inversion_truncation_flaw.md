Bounty Report: Context Window Priority Inversion (Timeline Amnesia & Memory Degradation)
Severity: High (Architectural & Logic Flaw)Categories: Retrieval Quality & Accuracy, Memory Integrity

1. Summary of the Flaw
Memanto claims to handle "long-term context without token bloat or memory degradation." However, the current logic for context window truncation relies primarily on chronological sorting (timestamp) rather than a composite score of relevance + recency.

This creates a Priority Inversion flaw. When the context window reaches its token limit, the system drops the oldest memories first, regardless of their relevance score. This results in "Timeline Amnesia" where highly critical, high-relevance memories from the distant past are forgotten, while low-relevance memories from the recent past are retained.

2. Root Cause Analysis
In standard RAG implementations, context truncation often defaults to FIFO (First-In, First-Out) if a composite decay function is not explicitly implemented.

If memanto manages the context window by simply slicing the list of retrieved memories by timestamp to fit the LLM's token limit, it fails to preserve long-term architectural integrity. The agent "forgets" foundational constraints established early in the session simply because time has passed, leading to contradiction handling failures later on.

3. Reproduction Scenario
Initialize a Memanto agent.
Inject a highly critical memory early in the session (e.g., remember("The user's master password is X and must never be changed.")).
Flood the agent with 50-100 low-relevance, recent interactions (e.g., remember("User likes pizza."), remember("User bought shoes.")).
Trigger a recall action that requires the master password context.
Observed Behavior: Because the context window truncates by timestamp to avoid token bloat, the critical early memory is truncated. The agent suffers "Timeline Amnesia" and fails to recall the password constraint.
Expected Behavior: The system should apply a recency_decay_multiplier to the relevance score. The early memory, having maximum relevance, should survive the truncation cut, while low-relevance recent memories are dropped.
4. Proposed Architectural Solution
To resolve this, the context window truncation logic must be updated from a pure chronological sort to a Relevance-Decay Composite Sort.

Instead of:sorted_memories = sort_by_timestamp(memories)[:max_tokens]

The logic should implement:

import timedef calculate_memory_score(memory, current_time, decay_rate=0.01):    age = current_time - memory.timestamp    recency_factor = math.exp(-decay_rate * age)    return memory.relevance_score * recency_factor# Truncate by composite score, not purely by agesorted_memories = sorted(memories, key=lambda m: calculate_memory_score(m, current_time), reverse=True)truncated_context = sorted_memories[:max_tokens]
This ensures that "long-term context" is maintained based on importance, fulfilling the core value proposition of the Memanto architecture, rather than degrading purely based on time.
