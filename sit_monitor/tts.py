"""跨平台 TTS 抽象：macOS 用 say，Windows 用 pyttsx3"""

import subprocess
import sys

from sit_monitor.i18n import t


def _default_voice():
    """根据当前语言返回默认 macOS 语音"""
    return t("platform.tts_voice")


def speak(text, voice=None, blocking=False):
    """播报文字。

    Args:
        text: 要播报的文字
        voice: macOS 语音名称，None 则根据语言自动选择
        blocking: 是否阻塞等待播放完成

    Returns:
        macOS 非阻塞时返回 Popen（可 terminate 打断），其余返回 None
    """
    if voice is None:
        voice = _default_voice()

    if sys.platform == "darwin":
        proc = subprocess.Popen(
            ["say", "-v", voice, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if blocking:
            proc.wait()
            return None
        return proc

    elif sys.platform == "win32":
        try:
            import pyttsx3
        except ImportError:
            return None

        engine = pyttsx3.init()
        from sit_monitor.i18n import get_language
        lang = get_language()
        for v in engine.getProperty("voices"):
            if lang == "zh" and ("chinese" in v.name.lower() or "zh" in v.id.lower()):
                engine.setProperty("voice", v.id)
                break
            elif lang == "en" and ("english" in v.name.lower() or "en" in v.id.lower()):
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
        return None

    return None
