"""Windows 平台：Toast 通知 + 媒体键控制"""

import sys


def is_in_call():
    """Windows 平台通话检测（暂未实现）"""
    return False


def send_notification(title, message, sound=False, use_notification_center=False, call_mute=False):
    """发送 Windows Toast 通知。"""
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="Sit Monitor",
            title=title,
            msg=message,
            duration="short",
        )
        if sound:
            toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        # winotify 不可用时静默降级
        print(f"[通知] {title}: {message}")

    if sound:
        from sit_monitor.tts import speak
        speech = message.replace("\n", "，")
        speak(speech)


def media_play_pause(browser=None):
    """模拟媒体播放/暂停键（VK_MEDIA_PLAY_PAUSE），所有浏览器都响应。"""
    import ctypes

    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    user32 = ctypes.windll.user32
    user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
