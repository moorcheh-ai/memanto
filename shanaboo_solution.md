```diff
--- a/README.md
+++ b/README.md
@@ -1,3 +1,59 @@
+<p align="center">
+    <a href="https://www.memanto.ai/">
+    <img alt="MEMANTO Logo" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-dark.svg" width="500">
+    </a>
+</p>
+
+<div align="center">
+  <h1>Memanto - Memory that AI Agents Love!</h1>
+</div>
+
+<p align="center">
+  <a href="https:/memanto.ai/">
+    <img src="https://img.shields.io/badge/Learn-More-000000?style=for-the-badge&logo=rocket&logoColor=white" alt="Learn More">
+  </a>
+  <a href="https://discord.gg/CyxRFQSQ3p">
+    <img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord">
+  </a>
+  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
+    <img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Setup Video">
+  </a>
+</p>
+
+<p align="center">
+    <a href="https://pypi.org/project/memanto/"><img alt="PyPI - Total Downloads" src="https://img.shields.io/pepy/dt/memanto.svg?color=blue&label=downloads"></a>
+    <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="Ask DeepWiki" src="https://deepwiki.com/badge.svg"></a>
+    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
+    <a href="https://pypi.org/project/memanto/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
+    <a href="https://x.com/moorcheh_ai" target="_blank"><img src="https://img.shields.io/twitter/url/https/twitter.com/langchain.svg?style=social&label=Follow%20%40Moorcheh.ai" alt="Twitter / X"></a>
+</p>
+
+
+<a href="https://www.star-history.com/?repos=moorcheh-ai%2Fmemanto&type=date&legend=top-left">
+ <picture>
+   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&theme=dark&legend=top-left" />
+   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&legend=top-left" />
+   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&legend=top-left" />
+ </picture>
+</a>
+
+---
+
+## What Is MEMANTO?
+
+**MEMANTO is a memory agent. It remembers, recalls, and answers — so your agents can achieve long-term goals and avoid confusion.**
+
+Most memory tools today are passive infrastructure: agents have to query them, parse the results, and figure out what to do next. MEMANTO is built differently. It's an active memory agent designed from the gaps agents themselves named when asked about their memory — three operations (`remember`, `recall`, `answer`) that give your agents persistent context across sessions, with state-of-the-art retrieval and zero ingestion latency.
+
+> *"My memory exists as a static snapshot injected into context — useful, but fundamentally passive. I can't query it, update it mid-conversation, express confidence levels, or distinguish between 'I know this' versus
+---
+
+## The Six Gaps
+
+| # | Gap | What MEMANTO does about it |
+| --- | --- | --- |
+| 1 | **Static injection** — memory arrives as a blob, not queryable by relevance | Queryable, not injectable |
+| 2 | **No temporal decay** — a preference from 6 months ago weighs the same as yesterday's deadline | Versioning, recency signals, temporal queries |
+| 3 | **No provenance** — can't tell explicit facts from inferred patterns or outdated info | Confidence + provenance metadata on every memory |
+| 4 | **Flat memory** — episodic, semantic, and procedural all collapsed to one layer | Typed and hierarchical — 13 built-in memory categories |
+| 5 | **No writeback** — contradictions silently coexist | Conflict detection, explicit versioning, no silent overwrites |
+| 6 | **Indexing delay** — mandatory LLM extraction, graph construction, and embedding delays | Zero ingestion latency, async indexing |
+
+We unpacked that into six concrete gaps and built MEMANTO to solve all six.
+
+### The Six Gaps
+
+| # | Gap | What MEMANTO does about it |
+| --- | --- | --- |
+| 1 | **Static injection** — memory arrives as a blob, not queryable by relevance | Queryable, not injectable |
+| 2 | **No temporal decay** — a preference from 6 months ago weighs the same as yesterday's deadline | Versioning, recency signals, temporal queries |
+| 3 | **No provenance** — can't tell explicit facts from inferred patterns or outdated info | Confidence + provenance metadata on every memory |
+| 4 | **Flat memory** — episodic, semantic, and procedural all collapsed to one layer | Typed and hierarchical — 13 built-in memory categories |
+| 5 | **No writeback** — contradictions silently coexist | Conflict detection, explicit versioning, no silent overwrites |
+| 6 | **Indexing delay** — mandatory LLM extraction, graph construction, and embedding delays | Zero ingestion latency, async indexing |
+
+We unpacked that into six concrete gaps and built MEMANTO to solve all six.
+
+### The Six Gaps
+
+| # | Gap | What MEMANTO does about it |
+| --- | --- | --- |
+| 1 | **Static injection** — memory arrives as a blob, not queryable by relevance | Queryable, not injectable