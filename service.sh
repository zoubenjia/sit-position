#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/sit_monitor.py"
LOG_DIR="$PROJECT_DIR/logs"
SESSION="sit-monitor"
SHELL_RC="$HOME/.zshrc"
MARKER="# sit-monitor auto-start"

usage() {
    echo "用法: $0 {install|uninstall|start|stop|restart|status|log}"
    echo ""
    echo "  install   安装自启动（iTerm2 打开时自动启动）"
    echo "  uninstall 卸载自启动"
    echo "  start     手动启动"
    echo "  stop      停止"
    echo "  restart   重启"
    echo "  status    查看状态"
    echo "  log       查看实时日志"
    exit 1
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
if command -v tmux &>/dev/null && [ -z "\${TMUX:-}" ]; then
    tmux has-session -t $SESSION 2>/dev/null || \
        tmux new-session -d -s $SESSION "$PYTHON $SCRIPT --auto-pause >> $LOG_DIR/sit-monitor.log 2>&1"
fi
EOF

    echo "已添加自启动到 $SHELL_RC"
    echo "下次打开 iTerm2 时会自动启动坐姿监控"
    echo "或运行 '$0 start' 立即启动"
}

do_uninstall() {
    do_stop 2>/dev/null || true
    if grep -q "$MARKER" "$SHELL_RC" 2>/dev/null; then
        # 删除 marker 行及其后 4 行
        sed -i '' "/$MARKER/,+4d" "$SHELL_RC"
        echo "已从 $SHELL_RC 移除自启动"
    else
        echo "未安装自启动"
    fi
}

do_start() {
    mkdir -p "$LOG_DIR"
    if tmux has-session -t $SESSION 2>/dev/null; then
        echo "已在运行中"
        return
    fi
    tmux new-session -d -s $SESSION "$PYTHON $SCRIPT --auto-pause >> $LOG_DIR/sit-monitor.log 2>&1"
    echo "已启动 (tmux session: $SESSION)"
}

do_stop() {
    if tmux has-session -t $SESSION 2>/dev/null; then
        tmux kill-session -t $SESSION
        echo "已停止"
    else
        echo "未在运行"
    fi
}

do_status() {
    if tmux has-session -t $SESSION 2>/dev/null; then
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

case "${1:-}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    start)     do_start ;;
    stop)      do_stop ;;
    restart)   do_stop 2>/dev/null; sleep 1; do_start ;;
    status)    do_status ;;
    log)       do_log ;;
    *)         usage ;;
esac
