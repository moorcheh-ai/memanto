## Savings report — ChatGPT memory vs Memanto

| Metric | ChatGPT (baseline) | Memanto (after) | Saved |
|--------|-------------------:|----------------:|------:|
| Stored memories | — | **43** | — |
| Tokens stored | — | 1,634 | — |
| Tokens / 28 days (12 queries/day) | 403,200 | 60,480 | **342,720 (85.0% fewer)** |
| p95 latency per recall | 1800 ms | 260 ms | **85.6% faster** |
| At-rest format | Opaque ChatGPT store | **OKF markdown** — git-diffable, portable, human-readable | Ownership |

> What migrating saves: you stop paying the ChatGPT context tax — every query no longer re-sends 1,200 tokens of history. Memanto retrieves only 180 relevant tokens. Over 28 days that's **342,720 tokens saved (85.0%)**.
>
> The bigger win is ownership: `OKF markdown: git-versioned, human-readable, portable — vs opaque ChatGPT store`.
