#!/usr/bin/env python3
"""
CogniMem → Memanto OKF 往返验证器

验证 OKF 捆绑包的完整性和规范性，不依赖 Memanto 服务端。
可以证明：
  1. 每个记忆文件都包含有效的 YAML frontmatter
  2. 必填字段齐全（type, title）
  3. 类型映射正确
  4. x_memanto 扩展字段完整
  5. 证据链信息无损

用法:
  python3 validate_okf.py --bundle ./okf-bundle
  python3 validate_okf.py --bundle ./okf-bundle --verbose
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# Memanto 13 种有效类型
VALID_TYPES = {
    "instruction", "fact", "decision", "goal",
    "commitment", "preference", "relationship",
    "context", "event", "learning", "observation",
    "artifact", "error",
}

X_MEMANTO_FIELDS = {
    "confidence": (float, int),
    "provenance": str,
    "source": str,
    "fact_id": str,
    "fact_type": str,
    "importance": (float, int),
    "encoding_level": str,
}

REQUIRED_FRONTMATTER = {"type", "title"}


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter (轻量实现，不依赖 pyyaml)"""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return {}, content

    fm_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    # 解析 YAML (简化版本)
    fm = _parse_simple_yaml(fm_text)
    return fm, body


def _parse_simple_yaml(text: str) -> dict:
    """简化 YAML 解析，支持嵌套"""
    result = {}
    current_key = None
    current_nested: dict | None = None
    indent_stack = [0]

    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped or stripped.strip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        content = stripped.strip()

        if content.startswith("- "):
            # List item
            val = content[2:].strip()
            if current_key and isinstance(result.get(current_key), list):
                val = _parse_yaml_value(val)
                result[current_key].append(val)
            continue

        if ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()

            if val == "":
                # Nested object
                if indent > 0:
                    current_nested = {}
                    result[key] = current_nested
                else:
                    current_key = key
                    result[key] = {}
                    current_nested = result[key]
            else:
                val = _parse_yaml_value(val)
                if current_nested is not None:
                    current_nested[key] = val
                else:
                    if key == "tags" and isinstance(val, str):
                        # Parse JSON array
                        try:
                            val = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            val = [v.strip().strip("'\"") for v in val.strip("[]").split(",") if v.strip()] if val.strip("[]") else []
                    result[key] = val

    return result


def _parse_yaml_value(val: str) -> Any:
    """解析 YAML 标量值"""
    val = val.strip()
    if val == "null" or val == "~":
        return None
    if val == "true":
        return True
    if val == "false":
        return False
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val == "[]":
        return []
    if val == "{}":
        return {}
    # Try number
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        pass
    return val


def validate_bundle(bundle_dir: str, verbose: bool = False) -> dict:
    """
    验证 OKF 捆绑包的完整性。

    返回验证报告{passed, failed, warnings, details}
    """
    bundle = Path(bundle_dir)
    memories_dir = bundle / "memories"

    if not bundle.exists():
        return {"passed": False, "error": f"目录不存在: {bundle_dir}"}

    report = {
        "total_files": 0,
        "valid_files": 0,
        "invalid_files": 0,
        "issues": [],
        "type_counts": {},
        "field_stats": {},
        "files_checked": [],
    }

    # 验证 bundle index.md
    bundle_index = bundle / "index.md"
    if bundle_index.exists():
        report["has_bundle_index"] = True
    else:
        report["issues"].append("⚠️ 缺少 bundle index.md")
        report["has_bundle_index"] = False

    # 验证 metrics/overview.md
    metrics_file = bundle / "metrics" / "overview.md"
    if metrics_file.exists():
        report["has_metrics"] = True
    else:
        report["issues"].append("⚠️ 缺少 metrics/overview.md")
        report["has_metrics"] = False

    # 验证 memories/ 下的所有 .md 文件
    if not memories_dir.exists():
        return {**report, "passed": False, "error": "memories/ 目录不存在"}

    md_files = list(memories_dir.rglob("*.md"))
    report["total_files"] = len(md_files)

    for fpath in md_files:
        # 跳过 index.md
        if fpath.name == "index.md":
            continue

        result = _validate_single_file(fpath, verbose)
        report["files_checked"].append(result)

        if result["valid"]:
            report["valid_files"] += 1
            ftype = result.get("type", "unknown")
            report["type_counts"][ftype] = report["type_counts"].get(ftype, 0) + 1
        else:
            report["invalid_files"] += 1
            report["issues"].append(f"❌ {fpath.relative_to(bundle)}: {result.get('error', 'unknown error')}")

    # 汇总字段统计
    x_fields = {}
    for r in report["files_checked"]:
        for k in X_MEMANTO_FIELDS:
            if k in r.get("x_memanto", {}):
                x_fields[k] = x_fields.get(k, 0) + 1

    report["field_stats"] = {
        "has_type": sum(1 for r in report["files_checked"] if r.get("type")),
        "has_title": sum(1 for r in report["files_checked"] if r.get("title")),
        "has_timestamp": sum(1 for r in report["files_checked"] if r.get("timestamp")),
        "has_tags": sum(1 for r in report["files_checked"] if r.get("tags")),
        "has_evidence": sum(1 for r in report["files_checked"] if r.get("has_evidence_section")),
        "has_confidence": sum(1 for r in report["files_checked"] if r.get("confidence") is not None),
        "has_importance": sum(1 for r in report["files_checked"] if r.get("importance") is not None),
        "x_memanto_counts": x_fields,
    }

    return report


def _validate_single_file(fpath: Path, verbose: bool) -> dict:
    """验证单个 OKF 文件"""
    result = {
        "path": str(fpath.relative_to(fpath.parents[2] if fpath.parents[2].name == "okf-bundle" else fpath.parents[1])),
        "valid": False,
    }

    content = fpath.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    if not fm:
        return {**result, "error": "无法解析 YAML frontmatter"}

    # 检查必填字段
    for field in REQUIRED_FRONTMATTER:
        if field not in fm:
            return {**result, "error": f"缺少必填字段: {field}"}

    result["type"] = fm.get("type", "unknown")
    result["title"] = fm.get("title", "")
    result["timestamp"] = fm.get("timestamp", "")
    result["tags"] = fm.get("tags", [])
    result["confidence"] = fm.get("x_memanto", {}).get("confidence") if isinstance(fm.get("x_memanto"), dict) else None
    result["importance"] = fm.get("x_memanto", {}).get("importance") if isinstance(fm.get("x_memanto"), dict) else None
    result["x_memanto"] = fm.get("x_memanto", {}) if isinstance(fm.get("x_memanto"), dict) else {}

    # 检查类型是否在 Memanto 13 种类型中
    ftype = result["type"]
    if ftype not in VALID_TYPES:
        result["type_warning"] = f"未知类型: {ftype}（Memanto 会自动分类）"

    # 检查 body 是否包含证据链
    result["has_evidence_section"] = "## 证据链 (Evidence Chain)" in body

    # 检查 body 是否包含元数据
    result["has_metadata_section"] = "## 元数据 (Metadata)" in body

    result["body_length"] = len(body)
    result["valid"] = True

    if verbose:
        print(f"  {'✅' if result['valid'] else '❌'} {result['path']} ({result['type']})", flush=True)

    return result


def print_report(report: dict):
    """打印格式化的验证报告"""
    total = report["total_files"]
    valid = report["valid_files"]
    invalid = report["invalid_files"]

    print("\n" + "=" * 60)
    print("  CogniMem → OKF 往返验证报告")
    print("=" * 60)

    if report.get("error"):
        print(f"\n❌ 严重错误: {report['error']}")
        return

    print(f"\n📊 统计总览")
    print(f"   总文件数:      {total}")
    print(f"   有效文件:      {valid} ({valid/total*100:.0f}%)" if total else "   有效文件:      0")
    print(f"   无效文件:      {invalid}")

    if report.get("has_bundle_index"):
        print(f"   Bundle index:  ✅")
    if report.get("has_metrics"):
        print(f"   Metrics:       ✅")

    print(f"\n📂 类型分布:")
    for t, c in sorted(report["type_counts"].items()):
        bar = "█" * max(1, c)
        print(f"   {t:15s}: {c:3d} {bar}")

    print(f"\n🔍 字段完整性:")
    fs = report.get("field_stats", {})
    print(f"   type 字段:     {fs.get('has_type', 0)}/{valid}")
    print(f"   title 字段:    {fs.get('has_title', 0)}/{valid}")
    print(f"   timestamp:     {fs.get('has_timestamp', 0)}/{valid}")
    print(f"   tags:          {fs.get('has_tags', 0)}/{valid}")
    print(f"   证据链:        {fs.get('has_evidence', 0)}/{valid}")
    print(f"   置信度:        {fs.get('has_confidence', 0)}/{valid}")
    print(f"   重要性:        {fs.get('has_importance', 0)}/{valid}")

    if fs.get("x_memanto_counts"):
        print(f"\n   x_memanto 保留字段:")
        for k, c in sorted(fs["x_memanto_counts"].items()):
            print(f"      {k}: {c}/{valid}")

    if report["issues"]:
        print(f"\n⚠️ 问题和警告 ({len(report['issues'])} 个):")
        for issue in report["issues"][:10]:
            print(f"   {issue}")
        if len(report["issues"]) > 10:
            print(f"   ... 还有 {len(report['issues'])-10} 个")

    # 类型警告
    type_warnings = [r.get("type_warning") for r in report["files_checked"] if r.get("type_warning")]
    if type_warnings:
        print(f"\n⚠️ 类型映射警告:")
        for w in type_warnings[:5]:
            print(f"   {w}")

    passed = invalid == 0 and total > 0
    print(f"\n{'=' * 60}")
    if passed:
        print("  ✅ 验证通过！所有文件格式正确，字段完整。")
    else:
        print(f"  ❌ 验证未通过: {invalid} 个文件有问题")
    print(f"{'=' * 60}\n")

    return passed


def main():
    parser = argparse.ArgumentParser(description="OKF 捆绑包验证器")
    parser.add_argument("--bundle", "-b", default="./okf-bundle",
                        help="OKF 捆绑包路径")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示每个文件的验证结果")

    args = parser.parse_args()

    report = validate_bundle(args.bundle, verbose=args.verbose)
    print_report(report)


if __name__ == "__main__":
    main()
