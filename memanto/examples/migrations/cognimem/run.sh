#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# CogniMem → Memanto 迁移 — 一键运行脚本
# ══════════════════════════════════════════════════════════════
#
# 用法:
#   ./run.sh                    # 从数据库导出 + OKF 生成
#   ./run.sh --dry-run          # 仅预览
#   ./run.sh --json export.json # 从 JSON 文件生成
#
# 环境变量:
#   COGNIMEM_DSN   PostgreSQL 连接串（默认: postgresql://cognimem@localhost/cognimem）
#   MEMANTO_AGENT  目标 Memanto agent ID（可选）
#
# ══════════════════════════════════════════════════════════════

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=""
JSON_INPUT=""
MEMANTO_AGENT="${MEMANTO_AGENT:-}"
COGNIMEM_DSN="${COGNIMEM_DSN:-postgresql://cognimem@localhost/cognimem}"

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN="--dry-run"; shift ;;
        --json) JSON_INPUT="$2"; shift 2 ;;
        --agent) MEMANTO_AGENT="$2"; shift 2 ;;
        --dsn) COGNIMEM_DSN="$2"; shift 2 ;;
        --help|-h)
            grep "^#" "$0" | grep -v "^#!/" | sed 's/^# //'
            exit 0
            ;;
        *) echo "未知选项: $1"; exit 1 ;;
    esac
done

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  CogniMem → Memanto 迁移                   ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── Step 1: 依赖检查 ──
echo "🔍 检查依赖..."
python3 -c "import yaml, json" 2>/dev/null || pip install -q pyyaml
echo "   ✅ Python 依赖就绪"

# ── Step 2: 生成 OKF 捆绑包 ──
OKF_DIR="$DIR/okf-bundle"
if [ -n "$JSON_INPUT" ]; then
    echo "📄 从 JSON 文件加载: $JSON_INPUT"
    python3 "$DIR/cognimem_to_okf.py" \
        --json "$JSON_INPUT" \
        --output "$OKF_DIR" \
        ${DRY_RUN}
elif [ -n "$COGNIMEM_DSN" ]; then
    echo "📡 连接数据库: $COGNIMEM_DSN"
    python3 "$DIR/cognimem_to_okf.py" \
        --dsn "$COGNIMEM_DSN" \
        --output "$OKF_DIR" \
        ${DRY_RUN}
else
    echo "❌ 未指定数据源（--json 或 --dsn）"
    exit 1
fi

if [ -n "$DRY_RUN" ]; then
    echo ""
    echo "🔍 预览模式完成。去掉 --dry-run 生成完整捆绑包。"
    exit 0
fi

# ── Step 3: Memanto 导入 ──
if command -v memanto &>/dev/null; then
    echo ""
    echo "📥 导入到 Memanto..."

    MEMANTO_ARGS=""
    if [ -n "$MEMANTO_AGENT" ]; then
        MEMANTO_ARGS="--agent $MEMANTO_AGENT"
    fi

    echo "   memanto migrate okf $OKF_DIR --dry-run $MEMANTO_ARGS"
    memanto migrate okf "$OKF_DIR" --dry-run $MEMANTO_ARGS

    echo ""
    echo "   ⚠️ 预览通过后，去掉 --dry-run 执行实际导入:"
    echo "   memanto migrate okf $OKF_DIR $MEMANTO_ARGS"
else
    echo ""
    echo "   ⚠️ memanto CLI 未安装，跳过导入。安装: pip install memanto"
fi

# ── Step 4: 汇总 ──
echo ""
echo "📋 迁移摘要:"
echo "   源: CogniMem 数据库"
echo "   目标: Memanto (OKF 捆绑包)"
echo "   捆绑包位置: $OKF_DIR"
echo "   查看: open $OKF_DIR/index.md"
echo ""
echo "✅ 完成!"
