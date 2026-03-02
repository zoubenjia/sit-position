#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.12"
VENV_DIR=".venv"

echo "=== 坐姿监控程序 - 环境搭建 ==="

# 检查依赖工具
if ! command -v uv &>/dev/null; then
    echo "未找到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v tmux &>/dev/null; then
    echo "提示: 未找到 tmux（后台运行需要，非必须）"
    if command -v brew &>/dev/null; then
        read -p "是否安装 tmux？[y/N] " yn
        if [[ "$yn" =~ ^[Yy]$ ]]; then
            brew install tmux
        fi
    else
        echo "  安装方式: brew install tmux"
    fi
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
