#!/usr/bin/env python3
"""
CogniMem → OKF (Open Knowledge Format) 迁移适配器

将 CogniMem 的记忆（事实三元组）导出为标准 OKF 捆绑包，
然后可以通过 memanto migrate okf 导入到 Memanto 中。

用法:
    # 直接从 CogniMem 数据库导出
    python3 cognimem_to_okf.py --dsn "postgresql://user:pass@host/db" --output ./okf-bundle

    # 从已有 JSON 导出文件生成
    python3 cognimem_to_okf.py --json ./cognimem_export.json --output ./okf-bundle

    # 仅预览统计信息
    python3 cognimem_to_okf.py --dsn "..." --dry-run

输出:
    okf-bundle/
    ├── index.md                    # 捆绑包导航
    ├── memories/
    │   ├── index.md                # 记忆类型目录
    │   ├── fact/                   # 按类型分组的记忆
    │   │   ├── index.md
    │   │   └── *.md                # 单个记忆文件
    │   ├── preference/
    │   ├── event/
    │   └── ...
    ├── daily-summaries/            # 每日摘要（如有）
    └── metrics/
        └── overview.md             # 统计概览
"""

import argparse
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ══════════════════════════════════════════════════════════════
# CogniMem → Memanto 类型映射
# ══════════════════════════════════════════════════════════════

# Memanto 支持的 13 种记忆类型
MEMANTO_TYPES = {
    "instruction", "fact", "decision", "goal",
    "commitment", "preference", "relationship",
    "context", "event", "learning", "observation",
    "artifact", "error",
}

# CogniMem 类型 → Memanto 类型
TYPE_MAP = {
    "preference": "preference",
    "fact": "fact",
    "goal": "goal",
    "decision": "decision",
    "observation": "observation",
    "skill": "learning",
    "action": "event",
    "general": "fact",
    "credential": "artifact",
    "error": "error",
    "instruction": "instruction",
    "commitment": "commitment",
    "relationship": "relationship",
    "context": "context",
}

# 中文类型名 → 英文（用于显示）
CN_TYPE_MAP = {
    "preference": "偏好",
    "fact": "事实",
    "goal": "目标",
    "decision": "决策",
    "observation": "观察",
    "learning": "学习",
    "event": "事件",
    "artifact": "制品",
    "instruction": "指令",
    "commitment": "承诺",
    "relationship": "关系",
    "context": "上下文",
    "error": "错误",
}


def slugify(text: str, max_len: int = 60) -> str:
    """将中文文本转为 URL 友好的英文 slug"""
    s = text.lower().strip()
    # 替换中文为拼音近似（简化：用 transliterate 库更好，但这里简单处理）
    # 去除非字母数字和连字符的字符
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[-\s]+', '-', s)
    s = s.strip('-')
    if not s:
        s = "memory"
    return s[:max_len].rstrip('-')


def map_fact_type(cognimem_type: str) -> str:
    """将 CogniMem 类型映射到 Memanto 类型"""
    t = cognimem_type.lower().strip()
    if t in TYPE_MAP:
        return TYPE_MAP[t]
    # 自动分类：未知类型保留给 Memanto 自动分类
    return t


def cognimem_fact_to_okf(fact: dict, idx: int) -> str:
    """
    将一条 CogniMem FactTriple 转为 OKF markdown 文件内容。

    OKF 格式:
    ---
    type: fact
    title: 用户 喜欢 冰美式
    description: 用户明确表示喜欢喝冰美式咖啡
    tags: [preference, drink]
    timestamp: 2026-07-01T10:30:00Z
    resource: session_xxx
    x_memanto:
        confidence: 0.85
        provenance: user_statement
        source: user
        fact_id: uuid
        importance: 0.7
        encoding_level: raw
        evidence: [...]
    ---
    用户 喜欢 冰美式

    证据:
    - 用户陈述: "我喜欢喝冰美式"
    """
    subject = fact.get("subject", "").strip()
    predicate = fact.get("predicate", "").strip()
    obj = fact.get("object", "").strip()
    fact_type = fact.get("fact_type", "general")
    confidence = fact.get("confidence", 0.6)
    importance = fact.get("importance", 0.5)
    encoding_level = fact.get("encoding_level", "raw")
    tags = fact.get("context_tags", []) or []
    evidence_list = fact.get("evidence", []) or []
    fact_id = fact.get("fact_id", str(uuid.uuid4()))
    source_session = fact.get("source_session", "")
    created_at = fact.get("created_at", "")
    accessed_at = fact.get("accessed_at", "")
    contradictions = fact.get("contradictions", []) or []
    connected_facts = fact.get("connected_facts", []) or []

    # 构建标题：subject predicate object
    title = f"{subject} {predicate} {obj}"
    if len(title) > 100:
        title = title[:97] + "..."

    # 构建描述：取第一条 evidence 的 statement
    description = ""
    for ev in evidence_list:
        stmt = (ev.get("statement") or "").strip()
        if stmt:
            description = stmt
            break
    if not description:
        description = title[:80]

    # 确定 Memanto 类型
    mapped_type = map_fact_type(fact_type)

    # 构建标签
    okf_tags = list(tags)
    if fact_type not in ("general",) and fact_type not in okf_tags:
        okf_tags.append(fact_type)
    if not okf_tags:
        okf_tags = [mapped_type]

    # 提取资源来源
    resource = ""
    for ev in evidence_list:
        src = (ev.get("source") or "").strip()
        if src:
            resource = src
            break
    if not resource and source_session:
        resource = source_session

    # 确定 provenance
    provenance_map = {
        "user_statement": "user",
        "user_confirmation": "user",
        "agent_inference": "agent",
        "tool_result": "tool",
        "system": "system",
        "memory_abstraction": "agent",
        "credential_store": "tool",
    }
    provenance = "user"
    for ev in evidence_list:
        src = (ev.get("source") or "").strip()
        if src in provenance_map:
            provenance = provenance_map[src]
            break

    # 构建 x_memanto 字段
    x_memanto = {
        "confidence": round(confidence, 4),
        "provenance": provenance,
        "source": provenance,
        "fact_id": fact_id,
        "fact_type": fact_type,
        "importance": round(importance, 4),
        "encoding_level": encoding_level,
    }
    if source_session:
        x_memanto["source_session"] = source_session
    if contradictions:
        x_memanto["contradictions"] = contradictions
    if connected_facts:
        x_memanto["connected_facts"] = connected_facts

    # 格式化时间
    def _fmt_ts(ts: str) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            return ts

    timestamp = _fmt_ts(created_at)

    # ── 构建 YAML frontmatter ──
    lines = ["---"]
    lines.append(f"type: {mapped_type}")
    lines.append(f"title: {_escape_yaml(title)}")
    lines.append(f"description: {_escape_yaml(description)}")
    lines.append(f"tags: {json.dumps(okf_tags, ensure_ascii=False)}")
    if timestamp:
        lines.append(f"timestamp: {timestamp}")
    if resource:
        lines.append(f"resource: {_escape_yaml(resource)}")
    lines.append("x_memanto:")
    for k, v in x_memanto.items():
        if isinstance(v, list):
            lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, str):
            lines.append(f"  {k}: {_escape_yaml(v)}")
        elif isinstance(v, bool):
            lines.append(f"  {k}: {str(v).lower()}")
        elif v is not None:
            lines.append(f"  {k}: {v}")
    lines.append("---")
    lines.append("")

    # ── Body：详细内容 ──
    lines.append(f"# {title}")
    lines.append("")

    # 描述（如果有且不等于标题）
    if description and description != title:
        lines.append(description)
        lines.append("")

    # 证据链
    if evidence_list:
        lines.append("## 证据链 (Evidence Chain)")
        lines.append("")
        for i, ev in enumerate(evidence_list, 1):
            src = (ev.get("source") or "unknown").replace("_", " ")
            stmt = (ev.get("statement") or "").strip()
            ts = _fmt_ts(ev.get("timestamp", ""))
            lines.append(f"- **来源**: {src}")
            if stmt:
                lines.append(f"  **陈述**: {stmt}")
            if ts:
                lines.append(f"  **时间**: {ts}")
            lines.append("")

    # 元数据
    lines.append("## 元数据 (Metadata)")
    lines.append("")
    lines.append(f"- **置信度**: {round(confidence * 100)}% ({_confidence_label(confidence)})")
    lines.append(f"- **重要性**: {round(importance * 100)}%")
    lines.append(f"- **编码级别**: {encoding_level}")
    lines.append(f"- **原始类型**: {fact_type}")
    if contradictions:
        lines.append(f"- **矛盾记录**: {len(contradictions)} 条")
    if connected_facts:
        lines.append(f"- **关联事实**: {len(connected_facts)} 条")
    lines.append(f"- **记忆ID**: `{fact_id}`")
    lines.append("")

    return "\n".join(lines)


def _escape_yaml(val: str) -> str:
    """YAML 安全转义"""
    if not val:
        return '""'
    if any(c in val for c in ':#{}[]&*!|>%@`"\'\\'):
        return json.dumps(val, ensure_ascii=False)
    return val


def _confidence_label(c: float) -> str:
    if c >= 0.9:
        return "确信"
    elif c >= 0.7:
        return "可靠"
    elif c >= 0.5:
        return "可能"
    elif c >= 0.3:
        return "存疑"
    return "不可靠"


# ══════════════════════════════════════════════════════════════
# OKF 捆绑包生成
# ══════════════════════════════════════════════════════════════

def write_okf_bundle(facts: list[dict], output_dir: str, dry_run: bool = False) -> dict:
    """
    将事实列表写入 OKF 捆绑包目录。
    返回统计信息。
    """
    output_path = Path(output_dir)

    # 按类型分组
    by_type: dict[str, list[dict]] = defaultdict(list)
    type_counts: dict[str, int] = defaultdict(int)
    total = len(facts)

    for fact in facts:
        mapped = map_fact_type(fact.get("fact_type", "general"))
        by_type[mapped].append(fact)
        type_counts[mapped] += 1

    stats = {
        "total_facts": total,
        "by_type": dict(type_counts),
        "agents": len(set(f.get("agent_id", "default") for f in facts)),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if dry_run:
        print(f"\n📊 CogniMem → OKF 迁移预览")
        print(f"{'=' * 50}")
        print(f"总事实数:       {total}")
        print(f"Agent 数:       {stats['agents']}")
        print(f"目标类型数:     {len(by_type)}")
        print(f"\n按 Memanto 类型分布:")
        for t, items in sorted(by_type.items()):
            cn = CN_TYPE_MAP.get(t, t)
            pct = len(items) / total * 100 if total else 0
            print(f"  {t:15s} ({cn:4s}): {len(items):3d} 条 ({pct:.0f}%)")
        return stats

    # ── 写入文件 ──
    print(f"\n📝 正在生成 OKF 捆绑包到: {output_path}")

    # memories/ 目录
    memories_dir = output_path / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # 每个类型一个子目录
    for mem_type, items in by_type.items():
        type_dir = memories_dir / mem_type
        type_dir.mkdir(parents=True, exist_ok=True)

        for i, fact in enumerate(items):
            filename = _fact_filename(fact, i)
            content = cognimem_fact_to_okf(fact, i)
            filepath = type_dir / filename
            filepath.write_text(content, encoding="utf-8")

        # 类型索引页
        _write_type_index(type_dir, mem_type, items)
        print(f"  ✅ {mem_type}/  ({len(items)} 条)")

    # memories/index.md
    _write_memories_index(memories_dir, by_type)

    # index.md (捆绑包根目录)
    _write_bundle_index(output_path, stats, by_type)

    # metrics/overview.md
    _write_metrics(output_path, stats, by_type)

    print(f"\n✅ OKF 捆绑包生成完成!")
    print(f"   位置: {output_path}")
    print(f"   总事实: {total}")
    print(f"   目录数: {len(by_type)}")

    return stats


def _fact_filename(fact: dict, idx: int) -> str:
    """生成单个记忆文件的文件名"""
    subject = (fact.get("subject") or "").strip()
    predicate = (fact.get("predicate") or "").strip()
    obj = (fact.get("object") or "").strip()
    base = slugify(f"{subject}-{predicate}-{obj}")
    if not base or len(base) < 3:
        base = f"memory-{idx}"
    fact_id = (fact.get("fact_id") or "")[:8]
    if fact_id:
        return f"{base}-{fact_id}.md"
    return f"{base}-{idx}.md"


def _write_type_index(type_dir: Path, mem_type: str, items: list[dict]):
    """为每个类型目录生成索引文件"""
    cn_name = CN_TYPE_MAP.get(mem_type, mem_type)
    total = len(items)

    # 按置信度分组统计
    high = sum(1 for f in items if (f.get("confidence") or 0) >= 0.7)
    med = sum(1 for f in items if 0.4 <= (f.get("confidence") or 0) < 0.7)
    low = sum(1 for f in items if (f.get("confidence") or 0) < 0.4)

    lines = [
        "---",
        f"type: {mem_type}",
        f"title: {cn_name}记忆 - 共{total}条",
        f"description: CogniMem 迁移的 {cn_name} 类型记忆，共{total}条",
        "---",
        "",
        f"# {cn_name}记忆",
        "",
        f"本目录包含从 CogniMem 迁移的 **{total} 条** {cn_name} 记忆。",
        "",
        "## 统计",
        "",
        f"- 高置信度 (≥70%): {high}",
        f"- 中置信度 (40-70%): {med}",
        f"- 低置信度 (<40%): {low}",
        "",
        "## 记忆列表",
        "",
    ]

    for i, fact in enumerate(items):
        subject = fact.get("subject", "").strip()
        predicate = fact.get("predicate", "").strip()
        obj = fact.get("object", "").strip()
        confidence = fact.get("confidence", 0.6)
        title = f"{subject} {predicate} {obj}"
        if len(title) > 80:
            title = title[:77] + "..."

        filename = _fact_filename(fact, i)
        pct = round(confidence * 100)
        icon = "🟢" if confidence >= 0.7 else "🟡" if confidence >= 0.4 else "🔴"
        lines.append(f"- [{icon} {title}]({mem_type}/{filename}) (置信度: {pct}%)")

    type_dir.joinpath("index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_memories_index(memories_dir: Path, by_type: dict[str, list[dict]]):
    """生成 memories/index.md"""
    total = sum(len(v) for v in by_type.values())
    lines = [
        "---",
        "title: 记忆目录 - 共{}条".format(total),
        "description: CogniMem 迁移的所有记忆，按 Memanto 类型分组",
        "---",
        "",
        "# 记忆目录 (Memories)",
        "",
        f"此目录包含从 CogniMem 迁移的 **{total} 条** 记忆，按类型分组。",
        "",
        "## 类型索引",
        "",
    ]

    for mem_type in sorted(by_type.keys()):
        cn = CN_TYPE_MAP.get(mem_type, mem_type)
        count = len(by_type[mem_type])
        lines.append(f"- **[{cn}]({mem_type}/)** — {count} 条记忆")

    lines.append("")
    lines.append("## 统计总览")
    lines.append("")
    lines.append("| 类型 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    for mem_type in sorted(by_type.keys()):
        cn = CN_TYPE_MAP.get(mem_type, mem_type)
        count = len(by_type[mem_type])
        pct = count / total * 100 if total else 0
        lines.append(f"| {cn} | {count} | {pct:.0f}% |")

    memories_dir.joinpath("index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_bundle_index(output_path: Path, stats: dict, by_type: dict[str, list[dict]]):
    """生成捆绑包根目录 index.md"""
    total = stats["total_facts"]
    agents = stats["agents"]

    lines = [
        "---",
        "title: CogniMem 记忆导出 - OKF 捆绑包",
        f"description: 通过 CogniMem → OKF 适配器迁移的记忆，共{total}条",
        f"timestamp: {stats['timestamp']}",
        "tags: [cognimem, migration, memory]",
        "x_memanto:",
        "  source: cognimem-migration-adapter",
        "  adapter_version: 1.0.0",
        "---",
        "",
        "# 🧠 CogniMem 记忆导出",
        "",
        f"> 通过 CogniMem → OKF 迁移适配器导出 • {total} 条记忆 • {agents} 个 Agent",
        "",
        "## 捆绑包结构",
        "",
        "```",
        "okf-bundle/",
        "├── index.md              # 此文件",
        "├── memories/",
        "│   ├── index.md          # 记忆目录",
    ]

    for mem_type in sorted(by_type.keys()):
        cn = CN_TYPE_MAP.get(mem_type, mem_type)
        lines.append(f"│   ├── {mem_type}/        # {cn}记忆")

    lines.extend([
        "│   │   ├── index.md",
        "│   │   └── *.md",
        "├── metrics/",
        "│   └── overview.md       # 统计概览",
        "```",
        "",
        "## 使用方法",
        "",
        "```bash",
        "# 1. 将此捆绑包导入 Memanto",
        "memanto migrate okf ./okf-bundle --dry-run    # 预览",
        "memanto migrate okf ./okf-bundle --agent my-agent  # 执行",
        "",
        "# 2. 或从 Memanto 导出为 OKF（往返验证）",
        "memanto memory export --okf",
        "```",
        "",
        "## 迁移摘要",
        "",
        f"从 CogniMem 数据库读取了 **{total}** 条事实三元组，映射到 **{len(by_type)}** 种 Memanto 记忆类型。",
        "",
        "- **源系统**: CogniMem（认知记忆系统）",
        "- **目标系统**: Memanto + OKF",
        "- **导出时间**: {stats['timestamp']}",
        "- **适配器版本**: 1.0.0",
    ])

    output_path.joinpath("index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_metrics(output_path: Path, stats: dict, by_type: dict[str, list[dict]]):
    """生成 metrics/overview.md"""
    metrics_dir = output_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    total = stats["total_facts"]

    # ASCII 柱状图
    max_count = max((len(v) for v in by_type.values()), default=1)
    bar_max = 30

    lines = [
        "---",
        "title: CogniMem 迁移统计",
        "description: 迁移数据统计总览",
        "---",
        "",
        "# 📊 CogniMem 迁移统计",
        "",
        f"生成时间: {stats['timestamp']}",
        "",
        "## 总览",
        "",
        f"- **总记忆数**: {total}",
        f"- **Agent 数**: {stats['agents']}",
        f"- **记忆类型数**: {len(by_type)}",
        "",
        "## 类型分布",
        "",
        "```",
    ]

    for mem_type in sorted(by_type.keys()):
        cn = CN_TYPE_MAP.get(mem_type, mem_type)
        count = len(by_type[mem_type])
        bar_len = max(1, int(count / max_count * bar_max))
        bar = "█" * bar_len
        pct = count / total * 100 if total else 0
        lines.append(f" {mem_type:15s} ({cn:4s}) |{bar} {count} ({pct:.0f}%)")

    lines.append("```")
    lines.append("")
    lines.append("## 置信度分布")
    lines.append("")

    high = sum(1 for v in by_type.values() for f in v if (f.get("confidence") or 0) >= 0.7)
    med = sum(1 for v in by_type.values() for f in v if 0.4 <= (f.get("confidence") or 0) < 0.7)
    low = sum(1 for v in by_type.values() for f in v if (f.get("confidence") or 0) < 0.4)

    total_ck = high + med + low
    if total_ck:
        hb = max(1, int(high / total_ck * bar_max))
        mb = max(1, int(med / total_ck * bar_max))
        lb = max(1, int(low / total_ck * bar_max))
        lines.append("```")
        lines.append(f" 高 (≥70%)  |{'█' * hb} {high} ({high/total_ck*100:.0f}%)")
        lines.append(f" 中 (40-70%)|{'█' * mb} {med} ({med/total_ck*100:.0f}%)")
        lines.append(f" 低 (<40%)  |{'█' * lb} {low} ({low/total_ck*100:.0f}%)")
        lines.append("```")

    metrics_dir.joinpath("overview.md").write_text("\n".join(lines), encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# CogniMem 数据库读取
# ══════════════════════════════════════════════════════════════

def connect_db(dsn: str):
    """连接 CogniMem PostgreSQL 数据库"""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    conn.set_session(autocommit=True)
    return conn


def fetch_facts_from_db(conn, agent_id: str = "") -> list[dict]:
    """从数据库读取所有事实"""
    import psycopg2
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if agent_id:
            cur.execute(
                "SELECT * FROM facts WHERE agent_id = %s ORDER BY confidence DESC",
                (agent_id,)
            )
        else:
            cur.execute("SELECT * FROM facts ORDER BY confidence DESC")

        rows = []
        for row in cur.fetchall():
            d = dict(row)
            # 解析 JSON 字段
            for field in ("evidence", "contradictions", "connected_facts"):
                if field in d and isinstance(d[field], str):
                    try:
                        d[field] = json.loads(d[field])
                    except (json.JSONDecodeError, TypeError):
                        d[field] = []
            # context_tags 可能是 pg array
            if "context_tags" in d and isinstance(d["context_tags"], str):
                # PostgreSQL array literal: {a,b,c}
                val = d["context_tags"].strip("{}")
                d["context_tags"] = [x.strip().strip('"') for x in val.split(",") if x.strip()] if val else []
            rows.append(d)
        return rows


def export_db_to_json(conn, output_path: str, agent_id: str = ""):
    """将数据库导出为 JSON 文件（用于离线处理）"""
    facts = fetch_facts_from_db(conn, agent_id)
    export = {
        "source": "CogniMem",
        "adapter": "cognimem_to_okf",
        "version": "1.0.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_facts": len(facts),
        "facts": facts,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2, default=str)
    print(f"📦 已导出 {len(facts)} 条事实到 {output_path}")
    return facts


def load_facts_from_json(json_path: str) -> list[dict]:
    """从 JSON 导出文件加载事实"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    facts = data.get("facts", [])
    print(f"📄 从 JSON 加载了 {len(facts)} 条事实 (来自 {data.get('source', 'unknown')})")
    return facts


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CogniMem → OKF 迁移适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  # 从数据库导出并生成 OKF 捆绑包
  python3 cognimem_to_okf.py --dsn "postgresql://cognimem:cognimem@localhost/cognimem" --output ./okf-bundle

  # 先导出为 JSON，再生成 OKF
  python3 cognimem_to_okf.py --dsn "postgresql://..." --json ./export.json
  python3 cognimem_to_okf.py --json ./export.json --output ./okf-bundle

  # 仅预览
  python3 cognimem_to_okf.py --dsn "..." --dry-run
        """
    )
    parser.add_argument("--dsn", help="CogniMem PostgreSQL 连接串")
    parser.add_argument("--json", help="从 JSON 文件加载事实（替代数据库直连）")
    parser.add_argument("--output", "-o", help="OKF 捆绑包输出目录")
    parser.add_argument("--agent", help="仅迁移指定 agent（默认全部）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不生成文件")
    parser.add_argument("--export-json", help="将数据库导出为 JSON 文件")

    args = parser.parse_args()

    if not args.dsn and not args.json:
        print("❌ 需要 --dsn 或 --json 参数")
        parser.print_help()
        sys.exit(1)

    # ── 加载数据 ──
    facts = []
    if args.json:
        facts = load_facts_from_json(args.json)
    elif args.dsn:
        try:
            import psycopg2
        except ImportError:
            print("❌ 需要 psycopg2: pip install psycopg2-binary")
            sys.exit(1)
        conn = connect_db(args.dsn)
        # 先加载数据库中的事实
        facts = fetch_facts_from_db(conn, args.agent or "")
        print(f"📡 从数据库读取了 {len(facts)} 条事实")

        # 可选：导出 JSON
        if args.export_json:
            export_db_to_json(conn, args.export_json, args.agent or "")
        conn.close()

    if not facts:
        print("⚠️ 没有事实数据")
        sys.exit(0)

    # ── 生成 OKF 捆绑包 ──
    stats = write_okf_bundle(facts, args.output or "./okf-bundle", dry_run=args.dry_run)

    if args.dry_run:
        print("\n运行 --output ./okf-bundle 生成完整捆绑包")
    else:
        print(f"\n📋 下一步:")
        print(f"   memanto migrate okf {args.output or './okf-bundle'} --dry-run")
        print(f"   memanto migrate okf {args.output or './okf-bundle'} --agent <agent-id>")


if __name__ == "__main__":
    main()
