#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/sit_monitor.py"
LOG_DIR="$PROJECT_DIR/logs"
SESSION="sit-monitor"
TRAY_PID_FILE="$PROJECT_DIR/.tray.pid"
# 自动检测用户 shell 配置文件
case "$(basename "$SHELL")" in
    zsh)  SHELL_RC="$HOME/.zshrc" ;;
    bash) SHELL_RC="$HOME/.bashrc" ;;
    *)    SHELL_RC="$HOME/.profile" ;;
esac
MARKER="# sit-monitor auto-start"

usage() {
    echo "用法: $0 {install|uninstall|start|stop|restart|status|log|update}"
    echo ""
    echo "  install   安装自启动（登录时自动启动托盘）"
    echo "  uninstall 卸载自启动"
    echo "  start     启动（托盘模式，后台运行）"
    echo "  stop      停止"
    echo "  restart   重启"
    echo "  status    查看状态"
    echo "  log       查看实时日志"
    echo "  update    从 GitHub 拉取最新代码并重启"
    exit 1
}

_tray_running() {
    [ -f "$TRAY_PID_FILE" ] && kill -0 "$(cat "$TRAY_PID_FILE")" 2>/dev/null
}

do_install() {
    if [ ! -f "$PYTHON" ]; then
        echo "错误: 未找到虚拟环境，请先运行 bash setup.sh"
        exit 1
    fi

    mkdir -p "$LOG_DIR"

    # 检查是否已安装
    if grep -q "$MARKER" "$SHELL_RC" 2>/dev/null; then
        echo "已安装，跳过"
        return
    fi

    cat >> "$SHELL_RC" << EOF

$MARKER
if [ -z "\${TMUX:-}" ]; then
    bash "$PROJECT_DIR/service.sh" start 2>/dev/null &
fi
EOF

    echo "已添加自启动到 $SHELL_RC"
    echo "下次打开终端时会自动启动坐姿监控托盘"
    echo "或运行 '$0 start' 立即启动"
}

do_uninstall() {
    do_stop 2>/dev/null || true
    if grep -q "$MARKER" "$SHELL_RC" 2>/dev/null; then
        sed -i '' "/$MARKER/,+4d" "$SHELL_RC"
        echo "已从 $SHELL_RC 移除自启动"
    else
        echo "未安装自启动"
    fi
}

do_start() {
    mkdir -p "$LOG_DIR"

    # 先停掉旧的 tmux session（如果有）
    if command -v tmux &>/dev/null && tmux has-session -t $SESSION 2>/dev/null; then
        tmux kill-session -t $SESSION 2>/dev/null || true
    fi

    if _tray_running; then
        echo "已在运行中 (PID: $(cat "$TRAY_PID_FILE"))"
        return
    fi

    # 托盘模式需要 GUI 环境，用 nohup 后台启动
    nohup "$PYTHON" "$SCRIPT" --tray >> "$LOG_DIR/sit-monitor.log" 2>&1 &
    echo $! > "$TRAY_PID_FILE"
    echo "已启动托盘模式 (PID: $!)"
}

do_stop() {
    # 停 tray 进程
    if _tray_running; then
        kill "$(cat "$TRAY_PID_FILE")" 2>/dev/null
        rm -f "$TRAY_PID_FILE"
        echo "已停止"
        return
    fi
    # 兼容旧的 tmux session
    if command -v tmux &>/dev/null && tmux has-session -t $SESSION 2>/dev/null; then
        tmux kill-session -t $SESSION
        echo "已停止 (tmux)"
        return
    fi
    rm -f "$TRAY_PID_FILE"
    echo "未在运行"
}

do_status() {
    if _tray_running; then
        echo "状态: 运行中 (托盘模式, PID: $(cat "$TRAY_PID_FILE"))"
    elif command -v tmux &>/dev/null && tmux has-session -t $SESSION 2>/dev/null; then
        echo "状态: 运行中 (tmux session: $SESSION)"
        echo "查看: tmux attach -t $SESSION"
    else
        echo "状态: 未运行"
    fi
}

do_log() {
    echo "=== 实时日志 (Ctrl+C 退出) ==="
    tail -f "$LOG_DIR/sit-monitor.log" 2>/dev/null
}

do_update() {
    cd "$PROJECT_DIR"

    echo "检查更新..."
    git fetch origin 2>/dev/null

    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")

    if [ -z "$REMOTE" ]; then
        echo "错误: 无法获取远程版本"
        exit 1
    fi

    if [ "$LOCAL" = "$REMOTE" ]; then
        echo "已是最新版本"
        return
    fi

    echo "发现新版本，更新中..."
    git pull origin main

    # 检查依赖是否有变化
    if git diff "$LOCAL" "$REMOTE" --name-only | grep -q "requirements.txt"; then
        echo "依赖有变化，重新安装..."
        uv pip install --python "$PYTHON" -r requirements.txt
    fi

    # 如果正在运行，自动重启
    if _tray_running || { command -v tmux &>/dev/null && tmux has-session -t $SESSION 2>/dev/null; }; then
        echo "重启服务..."
        do_stop
        sleep 1
        do_start
    fi

    echo "更新完成: $(git log --oneline -1)"
}

case "${1:-}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    start)     do_start ;;
    stop)      do_stop ;;
    restart)   do_stop 2>/dev/null; sleep 1; do_start ;;
    status)    do_status ;;
    log)       do_log ;;
    update)    do_update ;;
    *)         usage ;;
esac
