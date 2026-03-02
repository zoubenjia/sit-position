#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/sit_monitor.py"
LOG_DIR="$PROJECT_DIR/logs"
SESSION="sit-monitor"
TRAY_PID_FILE="$PROJECT_DIR/.tray.pid"
PLIST_NAME="com.zoubenjia.sit-monitor"
PLIST_SRC="$PROJECT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

usage() {
    echo "用法: $0 {install|uninstall|start|stop|restart|status|log|update}"
    echo ""
    echo "  install   安装 LaunchAgent 开机自启动"
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
    mkdir -p "$HOME/Library/LaunchAgents"

    # 生成 plist（替换路径占位符）
    sed \
        -e "s|__PYTHON__|$PYTHON|g" \
        -e "s|__SCRIPT__|$SCRIPT|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" \
        "$PLIST_SRC" > "$PLIST_DST"

    # 加载 LaunchAgent
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    launchctl load "$PLIST_DST"

    echo "已安装 LaunchAgent: $PLIST_DST"
    echo "登录时会自动启动坐姿监控托盘"
    echo "或运行 '$0 start' 立即启动"
}

do_uninstall() {
    do_stop 2>/dev/null || true

    # 卸载 LaunchAgent
    if [ -f "$PLIST_DST" ]; then
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "已卸载 LaunchAgent"
    fi

    # 兼容清理旧的 shell rc 方式
    for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile"; do
        if grep -q "# sit-monitor auto-start" "$rc" 2>/dev/null; then
            sed -i '' '/# sit-monitor auto-start/,+4d' "$rc"
            echo "已从 $rc 移除旧自启动"
        fi
    done
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

    nohup "$PYTHON" "$SCRIPT" --tray >> "$LOG_DIR/sit-monitor.log" 2>&1 &
    echo $! > "$TRAY_PID_FILE"
    echo "已启动托盘模式 (PID: $!)"
}

do_stop() {
    if _tray_running; then
        kill "$(cat "$TRAY_PID_FILE")" 2>/dev/null
        rm -f "$TRAY_PID_FILE"
        echo "已停止"
        return
    fi
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
    elif [ -f "$PLIST_DST" ]; then
        echo "状态: LaunchAgent 已安装，但未运行"
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

    if git diff "$LOCAL" "$REMOTE" --name-only | grep -q "requirements.txt"; then
        echo "依赖有变化，重新安装..."
        uv pip install --python "$PYTHON" -r requirements.txt
    fi

    if _tray_running; then
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
