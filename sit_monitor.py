#!/usr/bin/env python3
"""坐姿监控程序 - 使用 MacBook 摄像头检测不良坐姿并发送系统通知

用法:
  python sit_monitor.py --debug        # CLI debug 模式（显示画面）
  python sit_monitor.py --auto-pause   # CLI 后台模式
  python sit_monitor.py --tray         # 系统托盘模式
"""

from sit_monitor.__main__ import main

if __name__ == "__main__":
    main()
