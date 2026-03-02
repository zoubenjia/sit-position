"""跨平台 TTS 抽象：macOS 用 say，Windows 用 pyttsx3"""

import subprocess
import sys


def speak(text, voice="Tingting", blocking=False):
    """播报文字。

    Args:
        text: 要播报的文字
        voice: macOS 语音名称（Windows 自动选择中文声音）
        blocking: 是否阻塞等待播放完成

    Returns:
        macOS 非阻塞时返回 Popen（可 terminate 打断），其余返回 None
    """
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
        # 尝试选择中文声音
        for v in engine.getProperty("voices"):
            if "chinese" in v.name.lower() or "zh" in v.id.lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
        return None

    return None
