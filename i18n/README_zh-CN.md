<p align="center"><a href="https://www.memanto.ai/"><img alt="MEMANTO 标志" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="500"></a></p>

<div align="center"><h1>AI 智能体喜爱的记忆</h1></div>
<h2 align="center"><em>Memanto 是一个记忆助手智能体，专门管理其他智能体的记忆。它筛选值得保留的内容、跨会话整合记忆，并在智能体启动时立即提供简报；同时，你仍然拥有它们学到的一切。</em></h2>

<p align="center">可自动配合 Claude Code、Cursor、Codex 及 20 多种其他智能体使用。可在语义后端与 Open Knowledge Format（LLM Wiki 风格的 *.md 文件）之间完整转换，因此你的记忆资产可以随时检查、导出或迁移。运行 <code>memanto migrate</code>，记忆就会随你而动。</p>
<p align="center"><code>pip install memanto</code></p>

<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="加入 Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="加入 Reddit"></a>
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4"><img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="设置视频"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="文档"></a>
</p>

---
## 什么是 MEMANTO？

**MEMANTO 是一个记忆智能体。它会记住、检索并回答问题，让你的智能体能够实现长期目标并避免混乱。**

如今大多数记忆工具都是被动基础设施：智能体必须自行查询、解析结果并判断下一步操作。MEMANTO 则不同。它是根据智能体在讨论自身记忆时指出的缺口设计的主动记忆智能体：通过三种操作（`remember`、`recall`、`answer`）为智能体提供跨会话的持久上下文，具备先进检索能力，且写入时零延迟。

<div align="center"><h1>Memanto 实际效果</h1><h2>没有 Memanto</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Before.gif" alt="之前" width="1100" style="border-radius: 8px;"><h2>连接 Memanto 后</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/After.gif" alt="之后" width="1100" style="border-radius: 8px;"></div>

## 2 分钟快速开始

支持 macOS、Linux 和 Windows。

**选项 A：完全本地运行（无需账户或 API 密钥）：**
```bash
pip install memanto
memanto           # 选择 "On-Prem"；将引导你完成 Docker + Ollama 设置
```
需要 Docker。所有内容都在你的机器上运行和保存。

**选项 B：免费云端（无需信用卡，约 60 秒）：**
```bash
pip install memanto
memanto           # 选择 "Cloud"；粘贴免费的 Moorcheh API 密钥
```
在此获取免费的 API：https://console.moorcheh.ai/api-keys

可随时通过 `memanto config backend` 在本地和云端之间切换。

---
## 你将获得什么

- **无需在每次上下文重置后重新解释代码库。** Memanto 在会话之间持续保存，智能体能从上次停止的位置继续。
- **减少用于重复上下文的 token。** 仅在相关时检索记忆，充分利用上下文窗口。
- **记忆写入即刻可搜索。** 没有索引等待，也没有写入时 LLM 提取的开销。
- **一次 `pip install` 即可。** 无需部署向量数据库、定义 schema、配置 reranker 或维护后端服务。
- **灵活部署。** 可完全本地运行、使用云端 SaaS、部署到自己的 VPC，或随时切换。

---
## 集成

支持 Claude Code、Cursor、Codex、Windsurf、Cline、Continue、Goose、GitHub Copilot 等。查看[完整列表 →](https://docs.memanto.ai/integrations/overview)

```bash
memanto connect <integration-tool-id> # 一条命令完成集成
#例如：memanto connect claude-code
```

---
## 六个缺口

| # | 缺口 | MEMANTO 的解决方式 |
| --- | --- | --- |
| 1 | **静态注入**：记忆以文本块进入上下文，无法按相关性查询 | 可查询，而非只注入 |
| 2 | **没有时间衰减**：6 个月前的偏好和昨天的截止日期权重相同 | 版本、时效信号和时间查询 |
| 3 | **没有来源信息**：无法区分明确事实、推断模式和过时信息 | 每条记忆都有置信度和来源元数据 |
| 4 | **扁平记忆**：情景、语义和程序性记忆混在一层 | 类型化、层级化，内置 13 类记忆 |
| 5 | **没有回写**：矛盾内容会悄然共存 | 冲突检测、显式版本控制、不会静默覆盖 |
| 6 | **索引延迟**：强制 LLM 提取和图谱构建形成瓶颈 | 无开销写入，写入时即可使用 |

> *“我的记忆是注入上下文的静态快照，有用，但本质上仍是被动的。”* 这句模型的话成为了 Memanto 的设计简报。

---
## 基准测试

- **LongMemEval 89.8%**、**LoCoMo 87.1%**，超过 Mem0、Zep 和 Letta。[公开数据集 →](https://huggingface.co/moorcheh)
- **三种原语，而不是两种**：`remember`、`recall` 和 `answer`；基于记忆生成 LLM 回答，无需额外 API 密钥。
- **单次查询检索。** 没有多阶段管道、图 schema 或 reranker。
- **类型化语义记忆。** 13 类，包括 `instruction`、`fact`、`decision`、`goal`、`preference`、`relationship` 等。

---
## 架构

Memanto 的检索由 [Moorcheh](https://moorcheh.ai) 提供支持，它是一个信息论语义引擎。它可作为本地 Docker 容器运行（免费、无需账户），也可作为免费云服务使用（10 万次免费操作）；`memanto` CLI 会为你管理两者。

<p align="center"><img alt="MEMANTO 架构" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="1000"></p>
### 本地部署
<p align="center"><img alt="MEMANTO 本地部署架构" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="1000"></p>

---
## 为什么选择 Moorcheh？

Moorcheh 是 Memanto 背后的语义检索引擎。不同于依赖近似搜索和索引管道的向量数据库，Moorcheh 使用信息论方法返回精确结果且没有索引延迟：写入一条记忆，立即就能搜索。

因此 Memanto 不需要独立的向量数据库、embedding 管道或重排序阶段。Moorcheh 引擎可为本地部署用户运行在 Docker 中，也可使用免费层的托管云服务。无论哪种方式，CLI `memanto` 都会处理。

---
## 设置与演示
<p align="center"><a href="https://www.youtube.com/watch?v=vEtOaoweIG4"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-demo.png" alt="设置视频"></a></p>
## 获得最佳体验的本地仪表板
<p align="center"><a href="https://www.youtube.com/watch?v=5n976CmzohE"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-uidashboard.png" alt="本地仪表板演示"></a></p>

---
## CLI 参考

| 功能 | 命令 | 说明 |
|---|---|---|
| 系统状态仪表板 | `memanto status` | 查看环境、配置、服务器健康状况、活动会话和已注册智能体。 |
| 本地 REST API 与 Web UI | `memanto serve`, `memanto ui` | 本地运行 MEMANTO REST API 并打开交互式浏览器界面。CLI 使用时可选。 |
| 智能体生命周期管理 | `memanto agent ...` | 创建、列出或删除智能体，激活或停用会话，并运行 `agent bootstrap`。 |
| 记忆捕获 | `memanto remember` | 保存单条记忆、从 JSON 批量导入，或用 `--from-conversation` 从聊天记录提取事实。 |
| 编辑与删除 | `memanto edit`, `memanto forget` | 更新已有记忆的字段或永久删除错误、过时的记忆。 |
| 文件上传 | `memanto upload` | 上传 .pdf、.docx、.xlsx、.json、.txt、.csv、.md 到智能体记忆命名空间；可立即通过 `recall` 搜索。 |
| 高级检索 | `memanto recall` | 使用过滤条件执行标准搜索和时间查询（`--as-of`、`--changed-since`）。 |
| 基于记忆的问答 | `memanto answer` | 使用检索到的记忆上下文生成 RAG 回答。 |
| 每日智能工作流 | `memanto daily-summary`, `memanto conflicts` | 生成摘要、检测矛盾并交互式地解决冲突。 |
| 会话与自动化 | `memanto session ...`, `memanto schedule ...` | 检查会话并启用计划的每日摘要。 |
| 记忆文件管道 | `memanto memory export`, `memanto memory sync` | 导出结构化 Markdown 并将 `MEMORY.md` 同步到项目。添加 `--okf` 可导出或同步 [Open Knowledge Format](https://docs.memanto.ai/integrations/okf) 包。 |
| 导入与迁移 | `memanto migrate` | 从 Mem0、Letta、Supermemory 或 [OKF](https://docs.memanto.ai/integrations/okf) 包导入记忆。 |
| 配置检查 | `memanto config show` | 检查 API 密钥、活动智能体和会话、服务器设置及计划时间。 |
| 多智能体集成 | `memanto connect ...` | 为 Claude Code、Codex、Cursor、Windsurf、Antigravity、Gemini CLI、Cline、Continue、OpenCode、Goose、Roo、GitHub Copilot 和 Augment 连接、移除或列出集成。 |

完整命令参考请见 [CLI 用户指南](https://docs.memanto.ai/cli)。

### 支持的记忆类型
`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

- 使用特定类型保存：`memanto remember "用户偏好简洁回答" --type preference`
- 搜索时按类型过滤：`memanto recall "用户沟通风格" --type preference`

---
## SDK
- **TypeScript / Node.js**：[ `@moorcheh-ai/memanto`](../sdks/typescript) 使用 `uvx` 启动本地 Memanto 服务器，并提供易用的 `Memanto` 客户端（`remember` / `recall` / `answer`）。

---
## REST API
Memanto 提供基于会话的 REST API。请在本地启动服务器：
```bash
memanto serve
```
完整端点参考位于 [docs.memanto.ai/api](https://docs.memanto.ai/api)，服务器运行时也可访问 `http://localhost:8000/docs`。

---
## 研究
[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://huggingface.co/papers/2604.22085)

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026}, eprint={2604.22085}, archivePrefix={arXiv}, primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---
## 支持
- **文档**：[https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**：[加入 Discord 服务器](https://memanto.ai/discord)
- **Reddit**：[加入 Reddit 社区](https://www.reddit.com/r/Memanto/)
- **邮箱**：support@moorcheh.ai
- **X / Twitter**：[@moorcheh_ai](https://x.com/moorcheh_ai)

---
**MIT 许可证**

<br>
<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_zh-CN.md">简体中文</a> | <a href="README_ja.md">日本語</a>
</p>