**PROPOSED ACTION:** Modify the README.md file to include a new section for the LangGraph Integration Challenge.

```markdown
# Memanto - Memory that AI Agents Love!

## LangGraph Integration Challenge

### The Challenge

LangGraph is the gold standard for stateful agents, but managing long-term memory across disjointed sessions or massive graphs is still a hurdle. We want to see the best example of Memanto acting as the long-term memory layer for a LangGraph agent.

### The Bounty

* $100 USD (Paid via BountyHub)
* The Winning Metric: The Merged PR with the highest Social Traction Score by June 1st 2026.

### How to Enter

1. Star the Repo: Help us reach our 1,000-star goal!
2. Build: Create a LangGraph workflow (e.g., a customer support agent or a research assistant) that uses memanto to store and retrieve "memories" outside of the standard LangGraph state.
3. Submit PR: Fork this repo and add your code to /examples/langgraph-memanto.
4. Amplify: Post a video/thread of your agent on X, LinkedIn, or Reddit. Tag #Memanto and @moorcheh-ai. Include the link to your post in the PR description.

### The "Social Traction" Formula (Automated Check)

To keep this objective and low-bandwidth for our team, we will only audit the top 5 PRs based on these metrics:

* X (Twitter): Likes (1pt) + RTs (3pts) + Bookmarks (3pts).
* GitHub: 👍 or 🚀 reactions on your PR (2pts each).
* Reddit post (5pts) and each upvote +(2pts)

### Technical Criteria

* Must demonstrate Cross-Session Recall (The agent remembers something from "yesterday" that isn't in the current thread's state).
* Clean, documented code in a single folder.
* A 30-second GIF or video link in the README.md.

### Example Code

```python
# Example code for LangGraph integration with Memanto
import langgraph
import memanto

# Initialize Memanto
mem = memanto.Memanto()

# Initialize LangGraph
lg = langgraph.LangGraph()

# Store a memory
lg.store_memory("Hello, world!")

# Retrieve a memory
memory = memanto.Memory()
memory.load(mem, "Hello, world!")

print(memory.value)  # Output: Hello, world!
```

### Submission Guidelines

* Fork this repo and add your code to /examples/langgraph-memanto.
* Submit a PR with a clear description of your submission.
* Include a link to your post on X, LinkedIn, or Reddit in the PR description.
```

**PROPOSED ACTION:** Add a new section to the README.md file to include a call to action for participants to submit their PRs.

```markdown
## Call to Action

We encourage you to participate in the LangGraph Integration Challenge and showcase your skills in building a stateful agent with Memanto. Submit your PRs by June 1st 2026 to be eligible for the $100 bounty.

Don't forget to follow the submission guidelines and include a link to your post on X, LinkedIn, or Reddit in the PR description.

Good luck, and let's see what you can build!
```