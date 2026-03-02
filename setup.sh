#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.12"
VENV_DIR=".venv"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 坐姿监控程序 - 环境搭建 ==="
echo ""

# --- 系统检查 ---

# macOS 检查
if [[ "$(uname)" != "Darwin" ]]; then
    echo "错误: 此程序仅支持 macOS"
    exit 1
fi

# Homebrew（可选，用于安装 tmux）
if ! command -v brew &>/dev/null; then
    echo "提示: 未找到 Homebrew（非必须，但安装 tmux 需要）"
    echo "  安装方式: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
fi

# uv
if ! command -v uv &>/dev/null; then
    echo "未找到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# tmux（后台运行需要，非必须）
if ! command -v tmux &>/dev/null; then
    echo "提示: 未找到 tmux（后台运行和自启动需要，前台运行不需要）"
    if command -v brew &>/dev/null; then
        read -p "是否安装 tmux？[y/N] " yn
        if [[ "$yn" =~ ^[Yy]$ ]]; then
            brew install tmux
        fi
    else
        echo "  安装方式: brew install tmux"
    fi
    echo ""
fi

# --- Python 环境 ---

if [ -d "$VENV_DIR" ]; then
    echo "虚拟环境已存在，跳过创建"
else
    echo "创建 Python $PYTHON_VERSION 虚拟环境..."
    if ! uv venv --python "$PYTHON_VERSION" "$VENV_DIR" 2>&1; then
        echo "错误: 无法创建 Python $PYTHON_VERSION 环境"
        echo "  uv 会自动下载 Python，请检查网络连接"
        exit 1
    fi
fi

echo "安装 Python 依赖..."
uv pip install --python "$VENV_DIR/bin/python" -r requirements.txt

# --- 模型文件 ---

MODEL_FILE="$SCRIPT_DIR/pose_landmarker_lite.task"
if [ -f "$MODEL_FILE" ]; then
    echo "模型文件已存在，跳过下载"
else
    echo "下载 MediaPipe Pose 模型（约 6MB）..."
    if curl -sSL -o "$MODEL_FILE" \
        https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task; then
        echo "模型下载完成 ($(du -h "$MODEL_FILE" | cut -f1))"
    else
        echo "错误: 模型下载失败，请检查网络连接"
        exit 1
    fi
fi

# --- 日志目录 ---
mkdir -p "$SCRIPT_DIR/logs"

# --- 完成 ---
echo ""
echo "=== 搭建完成 ==="
echo ""
echo "使用方式:"
echo "  source $VENV_DIR/bin/activate"
echo "  python sit_monitor.py --auto-pause     # CLI 后台模式"
echo "  python sit_monitor.py --debug          # debug 模式（显示画面）"
echo "  python sit_monitor.py --tray           # 系统托盘模式"
echo ""
if command -v tmux &>/dev/null; then
    echo "后台运行:"
    echo "  bash service.sh start                  # 启动后台服务"
    echo "  bash service.sh install                # 安装开机自启"
fi
