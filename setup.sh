#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.12"
VENV_DIR=".venv"

echo "=== 坐姿监控程序 - 环境搭建 ==="

# 检查 uv 是否安装
if ! command -v uv &>/dev/null; then
    echo "错误: 未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 创建虚拟环境
if [ -d "$VENV_DIR" ]; then
    echo "虚拟环境已存在，跳过创建"
else
    echo "创建 Python $PYTHON_VERSION 虚拟环境..."
    uv venv --python "$PYTHON_VERSION" "$VENV_DIR"
fi

# 安装依赖
echo "安装依赖..."
uv pip install --python "$VENV_DIR/bin/python" -r requirements.txt

# 下载模型文件
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_FILE="$SCRIPT_DIR/pose_landmarker_lite.task"
if [ -f "$MODEL_FILE" ]; then
    echo "模型文件已存在，跳过下载"
else
    echo "下载 MediaPipe Pose 模型..."
    curl -sSL -o "$MODEL_FILE" \
        https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
    echo "模型下载完成 ($(du -h "$MODEL_FILE" | cut -f1))"
fi

echo ""
echo "=== 搭建完成 ==="
echo "使用方式:"
echo "  source $VENV_DIR/bin/activate"
echo "  python sit_monitor.py --debug        # debug 模式（显示画面）"
echo "  python sit_monitor.py --bad-seconds 5 # 快速测试通知"
