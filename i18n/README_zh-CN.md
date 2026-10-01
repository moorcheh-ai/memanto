<p align="center">
  <a href="https://www.memanto.ai/">
    <img alt="Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="440">
  </a>
</p>

<h3 align="center">AI 智能体喜爱的记忆！</h3>

<p align="center">Memanto 是一个<strong>记忆智能体</strong>，负责管理其他智能体的记忆：<br>保留什么、哪些内容冲突、何时过期，以及谁需要知道。</p>

<p align="center">
  <a href="https://github.com/moorcheh-ai/memanto"><img alt="GitHub stars" src="https://img.shields.io/github/stars/moorcheh-ai/memanto?style=social"></a>
  <a href="https://pepy.tech/projects/memanto"><img alt="Downloads" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
  <a href="https://arxiv.org/abs/2604.22085"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2604.22085-b31b1b.svg"></a>
  <a href="https://pypi.org/project/memanto/"><img alt="PyPI" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
</p>

```bash
pip install memanto
```
<!-- ============================================================
     演示 GIF——影响最大的待补资源。assets/demo.gif
     VHS 磁带另行提供。少于 15 秒，少于 3 MB。
     ============================================================ -->
<p align="center">
  <img alt="15 秒了解 Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/demo.gif" width="900">
</p>

---
> **每个平台都会存储你的智能体记忆，但没有一个会管理它。** 跨平台管理记忆不符合它们的利益；这正是记忆智能体的工作。

持久化已经解决。Claude、Bedrock、Cursor 和任何向量存储都愿意保存智能体写入的内容，却不会提醒你两个智能体对认证服务持相反看法、旧偏好悄然盖过新决策，或新智能体即将重做已完成又撤销的工作。

存储只是文件柜。Memanto 是参谋长：决定放入什么、监督访问、解决矛盾、丢弃过时内容，并在每个智能体行动前为其简报。

---
## 它是智能体，不是 API

Memanto 不是你调用的库，而是运行在你的智能体群旁边、根据自身判断完成六项工作的第二个智能体。每项都是真实行为且有对应命令，不是路线图项目。

| | Memanto 的工作 | 运行命令 |
|---|---|---|
| **观察和提取** | 从短暂交互中提取持久知识——决策、偏好、事实、失败——而非整体归档对话记录。 | `memanto remember --from-conversation` |
| **整合** | 将提取的记忆合并为一个规范记忆资产；重复项折叠、片段汇合，重复观察会增强置信度。 | `memanto schedule enable` |
| **协调** | 新知识与旧知识冲突时进行替代而非追加，保留曾经相信什么及其时间。 | `memanto conflicts` |
| **遗忘** | 衰减、过期和刻意删除由策略执行；受管理的遗忘能让检索长期保持准确。 | `memanto forget` |
| **简报** | 行动前向智能体提供资产中最小的相关切片；智能体无需自行查询。 | `memanto agent bootstrap` |
| **迁移知识** | 通过 Open Knowledge Format，跨框架和供应商的智能体群共享一份记忆而非五个孤岛。 | `memanto memory export --okf` |

**它在你休息时也会工作。** `memanto schedule enable` 每天运行：整理新记忆、合并跨智能体重复项，并标记矛盾供你审阅。

---
## 60 秒建立受管理的智能体群

```bash
pip install memanto
memanto                            # "On-Prem"（Docker，无需账户）或 "Cloud"（免费密钥）
memanto connect claude-code        # 也支持：cursor, codex, windsurf, cline, goose, copilot…
```
现在智能体共享一个受管理的资产。无需改代码、无需 wrapper、无需重写智能体循环。

```bash
# backend-agent 在周一学到一件事
memanto remember "Auth migrated to JWT — session cookies deprecated" --type decision
# review-agent 从未见过该会话，却在周五知道它
memanto recall "how does auth work"
memanto answer  "why did we drop session cookies?"     # 有依据，无需额外 API 密钥
# 智能体群上周二相信什么？发布后有什么变化？
memanto recall "deployment policy" --as-of 2026-08-05
memanto recall "deployment policy" --changed-since v2.1
```
macOS、Linux、Windows。`memanto ui` 打开覆盖整个资产的本地仪表板，可浏览、搜索和审计。

---
## 拥有你的智能体记忆

这是两年后仍重要的部分，也是每个平台原生记忆功能试图阻止的部分。

**你的资产是一个文件。** `memanto memory export --okf` 提供[开放知识格式](https://docs.memanto.ai/integrations/okf)：纯 Markdown，可读、可 diff、可提交、可 grep；不是只能申请的专有导出，而是真正的工作格式。

**它可以迁移。** `memanto migrate` 可从 Mem0、Letta、Supermemory 或任意 OKF 包导入，反向同样适用。OKF 是任何框架或供应商（包括我们的竞争对手）都能实现的开放交换格式。

**它在你的机器上运行。** 本地 Docker + Ollama，无需账户和 API 密钥，内容不会离开你的基础设施；也可以使用免费云或自托管。`memanto config backend` 一条命令切换，资产随你而行。

**MIT。** 没有等待锁住有用部分的 open-core 层，没有功能开关、席位限制或突然撤走的服务。

没有锁定，因为没有可锁定之物。

---
## 安全与主权
<!-- ============================================================
     TODO — Majid：用你的加固工作补充此处。结构正确，细节由你提供。
     标记为 ⟨…⟩ 的项目需要输入。无法证实的内容请删除，不要弱化。
     ============================================================ -->
**在 on-prem 模式下，任何内容都不会离开你的机器。** Docker + Ollama，无账户、无出站调用；提取、整合、协调、简报的完整循环均在本地执行。

**默认按范围隔离。** 每个智能体拥有自己的命名空间；你准确配置它应知道的内容，别无其他。

**每个信念都可追溯。** 置信度、来源、出处和时间戳让你能够追溯某项信念何时、从何处进入智能体群。

**遗忘由你决定，而非副作用。** 记忆只有 `active` 或 `expired` 两种状态。它只会因你编写的策略而过期，并带有日期和规则名。过期记忆仍会清晰标记地被检索，`memanto memory restore` 可恢复它；删除是另一项明确操作。

---
## 按你的条件过期的记忆

每条记忆在策略使其退役前均为**活跃**。过期有记录、可审计、可逆；内容仍会在检索中出现，并标记为 `[EXPIRED]` 和过期原因。

```bash
memanto policy list-preset          # conservative / balanced / aggressive
memanto policy apply-preset balanced  # 完整显示后询问
memanto policy apply --dry-run      # 每条规则将使哪些内容过期
memanto policy apply                # 显示策略和匹配项后确认
```
策略位于 `~/.memanto/policies/<agent>.yaml`，由按类型的保留表和具名规则组成。第一条匹配规则优先，因此规则也可*固定*原本会过期的记忆：

```yaml
retention:
  context: 7d
  event: 30d
  preference: never          # 持久的用户事实不会过期
rules:
  - name: pinned
    match: {tags: [pinned]}
    expire_after: never      # 明确固定优先于表
  - name: low-confidence-guesses
    match: {provenance: [inferred], confidence_below: 0.5}
    expire_after: 14d
purge_expired_after: never   # 可选硬删除，默认关闭
```
检索会并列显示两种状态，可用 `--active` 或 `--expired` 缩小范围。`--as-of` 不受影响，仍可重建当时真实的内容，包括后来过期的记忆。

```bash
memanto memory expire mem-123       # 手动退役一条
memanto memory restore mem-123      # 再恢复它
```
夜间任务（`memanto schedule enable`）会执行清扫；未设置策略的智能体不会使任何内容过期。

---
## 不同于记忆存储
| | 记忆存储 | **Memanto** |
|---|---|---|
| 它是什么 | 带 SDK 的数据库：写入、嵌入、检索 | 对智能体群记忆有判断力的智能体 |
| 核心行为 | 持久化 | 筛选、协调、整合、遗忘、简报 |
| 谁决定保留什么 | 你，在应用代码中决定 | Memanto，依据你设置一次的策略 |
| 两个智能体意见相左时 | 最后一次写入静默胜出 | 两者都版本化并呈现供审阅 |
| 遗忘 | 你必须记得执行的 `DELETE` | 按计划运行的一等策略 |
| 范围 | 一个应用、一个栈、一个供应商的围墙 | 跨栈、跨供应商的智能体群 |
| 你的数据 | 理论上可导出 | 工作格式*就是*可移植 Markdown |

向量存储、文件系统和平台原生记忆功能都位于 Memanto *之下*，作为它管理的可插拔存储后端。

---
<p align="center">
  <strong>⭐ 如果 Memanto 正在管理你的智能体群记忆，请给仓库点星</strong><br>
  <sub>这会告诉我们继续以 MIT 许可、完全公开地构建它。</sub></p>

---
## 开发者体验

**只需一次 `pip install`。** 无需配置向量存储、embedding 管道、reranker、schema 迁移或后端；检索引擎随包提供。

**兼容你已在运行的工具。** `memanto connect claude-code`；Cursor、Codex、Windsurf、Cline、Continue、Goose、Copilot 等也一样，每个只需一个命令。

**写入即可搜索。** 没有写入时提取、无需重建图或等待索引队列；`remember` 返回后，所有智能体即可检索。

**有类型，不是一锅粥。** 13 个记忆类别：`instruction`、`fact`、`decision`、`goal`、`preference`、`relationship` 等，检索可以筛选。

**仪表板，不是日志文件。** `memanto ui` 管理整个资产；`memanto daily-summary` 提供变更摘要；`memanto status` 显示注册智能体、会话和健康状态。

---
<details><summary><strong>完整 CLI 参考</strong></summary>
<br>

| 能力 | 命令 | 作用 |
|---|---|---|
| 系统状态 | `memanto status` | 环境、配置、服务器健康、活动会话和注册智能体。 |
| 本地 REST API + Web UI | `memanto serve`, `memanto ui` | 本地运行 REST API 并打开交互式浏览器界面。 |
| 智能体生命周期 | `memanto agent ...` | 创建、列出、删除智能体，激活会话并运行 `agent bootstrap`。 |
| 大规模记忆捕获 | `memanto remember` | 单条记忆、批量 JSON 或用 `--from-conversation` 从聊天记录提取。 |
| 编辑和删除 | `memanto edit`, `memanto forget` | 更新字段或永久删除错误记忆。 |
| 文件摄取 | `memanto upload` | 将 .pdf、.docx、.xlsx、.json、.txt、.csv、.md 加入智能体命名空间。 |
| 高级检索 | `memanto recall` | 带筛选的标准搜索和时间查询（`--as-of`、`--changed-since`）。 |
| 有依据的回答 | `memanto answer` | 从检索到的记忆上下文生成回答。 |
| 每日智能 | `memanto daily-summary`, `memanto conflicts` | 摘要、矛盾检测和交互式解决。 |
| 会话和自动化 | `memanto session ...`, `memanto schedule ...` | 检查会话，启用每日定时运行。 |
| 资产导出和同步 | `memanto memory export`, `memanto memory sync` | 导出结构化 Markdown，同步项目中的 `MEMORY.md`；`--okf` 生成可移植的 [OKF](https://docs.memanto.ai/integrations/okf) 包。 |
| 导入和迁移 | `memanto migrate` | 从 Mem0、Letta、Supermemory 或 OKF 包导入。 |
| 配置 | `memanto config show` | API 密钥、活动智能体/会话、服务器设置和计划时间。 |
| 智能体群集成 | `memanto connect ...` | Claude Code、Codex、Cursor、Windsurf、Antigravity、Gemini CLI、Cline、Continue、OpenCode、Goose、Roo、GitHub Copilot、Augment。 |

**记忆类型：** `instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

```bash
memanto remember "User prefers concise answers" --type preference
memanto recall "user communication style" --type preference
```
完整参考：[CLI 用户指南](https://docs.memanto.ai/cli)
</details>

<details><summary><strong>安装选项：完全本地或免费云</strong></summary>
<br>

**完全本地。无需账户、无需 API 密钥，内容不会离开你的机器：**

```bash
pip install memanto
memanto           # 选择 "On-Prem"；引导 Docker + Ollama 设置
```
需要 Docker。

**免费云。无需信用卡，约 60 秒：**

```bash
pip install memanto
memanto           # 选择 "Cloud"；粘贴免费 API 密钥
```
免费密钥位于 [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys)：100K 次免费操作。

随时切换：`memanto config backend`
</details>

<details><summary><strong>架构</strong></summary>
<br>

检索由内置的信息论语义引擎提供，可作为本地 Docker 容器或免费云服务运行。`memanto` CLI 管理两者；底层存储可插拔，Memanto 是其上的智能体。
<p align="center">
  <img alt="架构" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="900">
</p>
**On-prem：**
<p align="center">
  <img alt="On-prem 架构" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="900">
</p>
</details>

<details><summary><strong>SDK 和 REST API</strong></summary>
<br>

**TypeScript / Node.js**：[`@moorcheh-ai/memanto`](../sdks/typescript) 通过 `uvx` 启动本地 Memanto 服务器，并提供易用客户端（`remember` / `recall` / `answer`）。

**REST API**：使用 `memanto serve` 启动。端点参考见 [docs.memanto.ai/api](https://docs.memanto.ai/api)，运行时也可访问 `http://localhost:8000/docs`。
</details>

---
## 观看实际效果
| | |
|---|---|
| [**检索不只是搜索**](https://youtu.be/zoKP4b_rUhY) — 6:20 | [**设置和演示**](https://www.youtube.com/watch?v=vEtOaoweIG4) |
| [**本地仪表板导览**](https://www.youtube.com/watch?v=5n976CmzohE) | [**文档 →**](https://docs.memanto.ai) |

---
## 研究
**[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://arxiv.org/abs/2604.22085)**

在公开检索基准中，我们报告 LongMemEval 89.8%、LoCoMo 87.1%。<!-- TODO：在此说明 reader model、judge model 和 subset；你应当让条件清晰可见。 --> 数据集和测试工具公开在 [huggingface.co/moorcheh](https://huggingface.co/moorcheh)，欢迎自行运行。

我们愿意直说一个限制：这些基准的跨项目分数不可直接比较。reader model、judge model、judge prompt 和检索预算都会让结果相差数分，任何两次发布的运行都没有共享配置。包括我们的数字在内，都应视为方向性指标。记忆智能体最终应衡量的是随时间变化的资产质量：矛盾率、陈旧度和第六个月的准确率。

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026},
      eprint={2604.22085},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---

## 社区
<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Reddit"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="文档"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/27378"><img src="https://trendshift.io/api/badge/repositories/27378" alt="Trendshift" width="220"></a>
  <!-- <a href="https://mcptoplist.com/server/glama%2Fmoorcheh-ai%2Fmemanto"><img src="https://mcptoplist.com/badge/glama%2Fmoorcheh-ai%2Fmemanto.svg" alt="MCP Top List" width="220"></a> -->
  <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
</p>

问题：[support@moorcheh.ai](mailto:support@moorcheh.ai) · [@moorcheh_ai](https://x.com/moorcheh_ai)

---
<p align="center">
  <strong>MIT 许可证</strong><br>
  <sub><a href="../README.md">English</a> · <a href="README_es.md">Español</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_ja.md">日本語</a></sub>
</p>
