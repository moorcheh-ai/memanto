# CogniMem → Memanto 迁移适配器

> 将 [CogniMem](https://github.com/1421906110/qwen-memoryagent) 认知记忆系统的记忆迁移到 Memanto，导出为标准 OKF（Open Knowledge Format）捆绑包，实现记忆的可携带性和供应商中立。

## 概览

[CogniMem](https://github.com/1421906110/qwen-memoryagent) 是一个以"事实三元组"为最小存储单位的认知记忆系统。本适配器将 CogniMem PostgreSQL 数据库中存储的**事实三元组**（subject-predicate-object）、**证据链**、**置信度**、**矛盾记录**等信息，无损映射到 Memanto 的 OKF 格式，然后通过 `memanto migrate okf` 导入。

### 迁移架构

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  CogniMem    │     │  OKF 捆绑包       │     │   Memanto    │
│  PostgreSQL  │ ──► │  (标准 markdown)  │ ──► │   Agent      │
│              │     │                  │     │              │
│  FactTriple  │     │  memories/       │     │  13 种记忆   │
│  52 条真实   │     │  fact/           │     │  类型分类    │
│  数据        │     │  preference/     │     │  完整映射    │
└─────────────┘     └──────────────────┘     └─────────────┘
```

## 前置条件

- Python 3.10+
- [Memanto CLI](https://docs.memanto.ai/cli) — `pip install memanto`
- CogniMem 数据库访问（PostgreSQL 连接串）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 一键迁移（数据库 → OKF → Memanto）
export COGNIMEM_DSN="postgresql://user:pass@host:5432/cognimem"
./run.sh

# 3. 或手动分步操作
python3 cognimem_to_okf.py --dsn "$COGNIMEM_DSN" --output ./okf-bundle
memanto migrate okf ./okf-bundle --dry-run
memanto migrate okf ./okf-bundle --agent my-agent
```

## 适配器用法

```bash
# 从数据库直接导出 + OKF 捆绑包
python3 cognimem_to_okf.py \
    --dsn "postgresql://cognimem@localhost/cognimem" \
    --output ./okf-bundle

# 首先导出为 JSON（离线使用）
python3 cognimem_to_okf.py \
    --dsn "postgresql://cognimem@localhost/cognimem" \
    --export-json ./cognimem_export.json

# 然后从 JSON 生成 OKF
python3 cognimem_to_okf.py \
    --json ./cognimem_export.json \
    --output ./okf-bundle

# 仅预览统计信息
python3 cognimem_to_okf.py --dsn "..." --dry-run

# 仅迁移特定 agent
python3 cognimem_to_okf.py \
    --dsn "..." \
    --agent "default" \
    --output ./okf-bundle
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COGNIMEM_DSN` | `postgresql://cognimem@localhost/cognimem` | 数据库连接串 |
| `MEMANTO_AGENT` | (活动 agent) | 目标 Memanto agent ID |

## 字段映射

### CogniMem FactTriple → OKF

| CogniMem 字段 | OKF 字段 | 说明 |
|--------------|----------|------|
| `subject + predicate + object` | `title` | "用户 喜欢 冰美式" |
| `fact_type` | `type` | 映射到 Memanto 的 13 种类型 |
| `evidence[0].statement` | `description` | 第一条证据的原文 |
| `context_tags` | `tags` | 直接复制 |
| `created_at` | `timestamp` | ISO 时间格式 |
| `evidence[0].source` | `resource` | 来源标识 |
| `confidence` | `x_memanto.confidence` | 保留原始值 |
| `importance` | `x_memanto.importance` | 保留原始值 |
| `encoding_level` | `x_memanto.encoding_level` | raw/compressed/core |
| `fact_id` | `x_memanto.fact_id` | 保留原始 UUID |
| `evidence` | `x_memanto.evidence` | 完整证据链 |
| `contradictions` | `x_memanto.contradictions` | 矛盾记录 ID 列表 |
| `source_session` | `x_memanto.source_session` | 来源会话 |
| Body | `全文` | 格式化为 markdown，含证据链和元数据 |

### 类型映射

CogniMem 的类型体系与 Memanto 的 13 种类型对比如下：

| CogniMem 类型 | Memanto 类型 | 说明 |
|--------------|-------------|------|
| `fact` | `fact` | 事实陈述 |
| `preference` | `preference` | 用户偏好 |
| `goal` | `goal` | 目标 |
| `decision` | `decision` | 决策 |
| `observation` | `observation` | 观察 |
| `skill` | `learning` | 学习成果 |
| `action` | `event` | 执行的事件 |
| `general` | `fact` | 一般事实 |
| `credential` | `artifact` | 凭证/密钥 |
| 未知类型 | (自动分类) | Memanto 的自动分类器处理 |

## 往返验证

适配器支持完整的 OKF 往返验证（Round-trip Validation）：

```
CogniMem → OKF export → Memanto import → OKF re-export → compare
```

1. 从 CogniMem 导出 → OKF 捆绑包
2. `memanto migrate okf ./okf-bundle` → 导入 Memanto
3. `memanto memory export --okf` → 从 Memanto 重新导出
4. 比较前后 OKF 捆绑包，验证字段完整性和一致性

往返过程中，`x_memanto` 字段保证 Memanto 特有的数据（confidence、provenance 等）被完整保留。

## 输出结构

```
okf-bundle/
├── index.md                    # 捆绑包导航
├── memories/
│   ├── index.md                # 类型目录
│   ├── fact/                   # 每类记忆一个目录
│   │   ├── index.md            # 类型索引（含统计）
│   │   └── *.md                # 单个记忆文件（OKF 格式）
│   ├── preference/
│   ├── event/
│   └── ...
└── metrics/
    └── overview.md             # 统计概览（ASCII 图表）
```

## 环境要求

- Python 3.10+（依赖 `psycopg2` 和 `pyyaml`）
- 访问运行中的 CogniMem PostgreSQL 数据库
- 可选：Memanto CLI（`pip install memanto`）用于导入

## 许可证

AGPL-3.0 — 与 CogniMem 主项目一致。

---

*"Own Your Agentic Memory" — Memanto Bounty #1609*
