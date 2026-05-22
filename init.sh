#!/usr/bin/env bash
# init.sh — 社媒数据面板项目启动与验证脚本
# 每次会话开始时运行此脚本，确保环境就绪

set -e

echo "=========================================="
echo "  社媒数据面板 - 环境初始化"
echo "=========================================="

# 1. 确认当前目录
echo ""
echo "[1/6] 确认项目根目录..."
if [ ! -f "CLAUDE.md" ]; then
    echo "❌ 错误：未在项目根目录。请 cd 到 social-media-dashboard/"
    exit 1
fi
echo "✅ 当前目录：$(pwd)"

# 2. 检查 Python 环境
echo ""
echo "[2/6] 检查 Python 环境..."
python3 --version || { echo "❌ Python3 未安装"; exit 1; }
echo "✅ Python 环境正常"

# 3. 检查依赖
echo ""
echo "[3/6] 检查依赖包..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q 2>/dev/null || echo "⚠️ 部分依赖安装失败，请手动检查"
    echo "✅ 依赖已检查"
else
    echo "⚠️ requirements.txt 不存在，跳过依赖检查"
fi

# 4. 检查数据目录
echo ""
echo "[4/6] 检查数据文件..."
SAMPLE_COUNT=$(find data/samples -name "*.csv" 2>/dev/null | wc -l)
DATA_COUNT=$(find data -maxdepth 1 -name "*.csv" 2>/dev/null | wc -l)
echo "  示例数据文件：${SAMPLE_COUNT} 个"
echo "  运营数据文件：${DATA_COUNT} 个"
if [ "$SAMPLE_COUNT" -eq 0 ] && [ "$DATA_COUNT" -eq 0 ]; then
    echo "⚠️ 无任何数据文件。如果 F02 已完成，请运行 python generate_sample_data.py"
else
    echo "✅ 数据文件就绪"
fi

# 5. 检查 harness 文件完整性
echo ""
echo "[5/6] 检查 harness 文件..."
MISSING=0
for f in CLAUDE.md feature_list.json claude-progress.md; do
    if [ ! -f "$f" ]; then
        echo "❌ 缺失：$f"
        MISSING=1
    fi
done
if [ "$MISSING" -eq 0 ]; then
    echo "✅ 所有 harness 文件完整"
else
    echo "⚠️ 请补全缺失的 harness 文件"
fi

# 6. 显示当前功能状态摘要
echo ""
echo "[6/6] 功能状态摘要..."
if command -v python3 &>/dev/null && [ -f "feature_list.json" ]; then
    python3 -c "
import json
with open('feature_list.json') as f:
    data = json.load(f)
total = len(data['features'])
done = sum(1 for ft in data['features'] if ft['status'] == 'done')
in_progress = sum(1 for ft in data['features'] if ft['status'] == 'in_progress')
not_started = sum(1 for ft in data['features'] if ft['status'] == 'not_started')
print(f'  总计：{total} 个功能')
print(f'  ✅ 已完成：{done}')
print(f'  🔄 进行中：{in_progress}')
print(f'  ⬜ 未开始：{not_started}')
print()
# 显示下一个待做的功能
for ft in data['features']:
    if ft['status'] != 'done':
        print(f'  👉 下一步：{ft[\"id\"]} - {ft[\"name\"]}')
        break
"
fi

echo ""
echo "=========================================="
echo "  初始化完成。可以开始工作了。"
echo "=========================================="
