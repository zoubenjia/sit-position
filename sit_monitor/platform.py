"""平台分发器：按 sys.platform 选择对应平台模块"""

import sys

if sys.platform == "darwin":
    from sit_monitor.platform_mac import send_notification, media_play_pause, is_in_call
elif sys.platform == "win32":
    from sit_monitor.platform_win import send_notification, media_play_pause, is_in_call
else:
    raise RuntimeError(f"不支持的平台: {sys.platform}")

__all__ = ["send_notification", "media_play_pause", "is_in_call"]
