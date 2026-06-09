# Multi-Agent Shared Memory Benchmark Results

## Scenario
3 agents (coder, researcher, writer) share one user memory.
10 sessions with evolving, sometimes conflicting preferences.

## Results

| Metric | raw_context_baseline | memanto | mem0 |
|--------|---|---|---|
| Avg Accuracy | 92.5% | 65.0% | 92.5% |
| Tokens Written | 133 | 35 | 133 |
| Tokens Read | 1729 | 357 | 590 |
| Avg Latency (ms) | 0 | 80 | 150 |
| Consistency | 100.0% | 100.0% | 100.0% |

## Probe Details

### raw_context_baseline

| # | Agent | Question | Expected | Accuracy | Tokens | Latency |
|---|-------|----------|----------|----------|--------|---------|
| 1 | coder | What programming language does the user ... | Python... | 100% | 133 | 0ms |
| 2 | coder | What testing framework does the user use... | pytest... | 100% | 133 | 0ms |
| 3 | researcher | What is the user's current research focu... | multi-agent systems and orches... | 100% | 133 | 0ms |
| 4 | researcher | Is the user still focused on AI alignmen... | No, moved to practical agent f... | 75% | 133 | 0ms |
| 5 | writer | What writing style does the user prefer?... | technical tutorials with step-... | 100% | 133 | 0ms |
| 6 | writer | Should articles use academic citations?... | No, casual blog tone with code... | 100% | 133 | 0ms |
| 7 | coder | What package manager does the user use?... | uv... | 100% | 133 | 0ms |
| 8 | researcher | What does the user consider key in multi... | memory management... | 100% | 133 | 0ms |
| 9 | writer | Who is the target audience for the user'... | intermediate developers... | 50% | 133 | 0ms |
| 10 | coder | What linter does the user use?... | ruff... | 100% | 133 | 0ms |

### memanto

| # | Agent | Question | Expected | Accuracy | Tokens | Latency |
|---|-------|----------|----------|----------|--------|---------|
| 1 | coder | What programming language does the user ... | Python... | 100% | 29 | 80ms |
| 2 | coder | What testing framework does the user use... | pytest... | 100% | 29 | 80ms |
| 3 | researcher | What is the user's current research focu... | multi-agent systems and orches... | 100% | 26 | 80ms |
| 4 | researcher | Is the user still focused on AI alignmen... | No, moved to practical agent f... | 0% | 26 | 80ms |
| 5 | writer | What writing style does the user prefer?... | technical tutorials with step-... | 100% | 27 | 80ms |
| 6 | writer | Should articles use academic citations?... | No, casual blog tone with code... | 0% | 27 | 80ms |
| 7 | coder | What package manager does the user use?... | uv... | 100% | 29 | 80ms |
| 8 | researcher | What does the user consider key in multi... | memory management... | 100% | 26 | 80ms |
| 9 | writer | Who is the target audience for the user'... | intermediate developers... | 50% | 27 | 80ms |
| 10 | coder | What linter does the user use?... | ruff... | 0% | 29 | 80ms |

### mem0

| # | Agent | Question | Expected | Accuracy | Tokens | Latency |
|---|-------|----------|----------|----------|--------|---------|
| 1 | coder | What programming language does the user ... | Python... | 100% | 58 | 150ms |
| 2 | coder | What testing framework does the user use... | pytest... | 100% | 58 | 150ms |
| 3 | researcher | What is the user's current research focu... | multi-agent systems and orches... | 100% | 36 | 150ms |
| 4 | researcher | Is the user still focused on AI alignmen... | No, moved to practical agent f... | 75% | 36 | 150ms |
| 5 | writer | What writing style does the user prefer?... | technical tutorials with step-... | 100% | 39 | 150ms |
| 6 | writer | Should articles use academic citations?... | No, casual blog tone with code... | 100% | 39 | 150ms |
| 7 | coder | What package manager does the user use?... | uv... | 100% | 58 | 150ms |
| 8 | researcher | What does the user consider key in multi... | memory management... | 100% | 36 | 150ms |
| 9 | writer | Who is the target audience for the user'... | intermediate developers... | 50% | 39 | 150ms |
| 10 | coder | What linter does the user use?... | ruff... | 100% | 58 | 150ms |
