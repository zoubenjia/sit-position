"""macOS 平台相关：通知、TTS、媒体控制"""

import re
import subprocess

from sit_monitor.i18n import t

# --------------- 通知 ---------------

def send_notification(title, message, sound=False, use_notification_center=False):
    """发送通知。返回 say 进程（如有），供调用方跟踪和终止。"""
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
    safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')

    if use_notification_center:
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
    else:
        btn_text = t("btn.ok")
        script = (
            f'display dialog "{safe_msg}" with title "{safe_title}" '
            f'buttons {{"{btn_text}"}} default button 1 giving up after 10'
        )
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if sound:
        voice = t("platform.tts_voice")
        speech = message.replace("\n", "，" if voice == "Tingting" else ", ")
        return subprocess.Popen(["say", "-v", voice, speech], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


# --------------- 媒体播放控制 ---------------

_BROWSERS = ["Firefox", "Google Chrome", "Safari", "Arc", "Brave Browser", "Microsoft Edge"]
_JS_BROWSERS = {"Google Chrome", "Arc", "Brave Browser", "Microsoft Edge"}
_VIDEO_JS = "document.querySelectorAll('video').forEach(v => v.paused ? v.play() : v.pause())"


def _detect_browser():
    """检测当前运行的浏览器"""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'],
        capture_output=True, text=True,
    )
    running = result.stdout.strip()
    running_lower = running.lower()
    for b in _BROWSERS:
        if b.lower() in running_lower:
            return b
    return None


def _is_browser_playing_media():
    """通过 macOS 电源管理断言检查是否有浏览器在播放音视频。

    浏览器播放音视频时，coreaudiod 会代其创建 audio-out 资源断言，
    格式：Created for PID: <browser_pid> + Resources: audio-out ...
    只有当 audio-out 断言的 PID 属于浏览器进程时才返回 True。
    """
    try:
        result = subprocess.run(
            ["pmset", "-g", "assertions"],
            capture_output=True, text=True, timeout=3,
        )
        # 匹配 "Created for PID: NNN" 紧跟 "Resources: audio-out" 的断言
        audio_pids = set()
        for m in re.finditer(
            r'Created for PID:\s*(\d+)\.\s*\n\s*Resources:.*audio-out',
            result.stdout,
        ):
            audio_pids.add(m.group(1))

        if not audio_pids:
            return False

        # 检查这些 PID 是否属于浏览器
        for pid in audio_pids:
            ps_out = subprocess.run(
                ["ps", "-p", pid, "-o", "comm="],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip().lower()
            if any(b.lower() in ps_out for b in _BROWSERS):
                return True

        return False
    except Exception:
        return True  # 检测失败时保守假设有播放


def media_play_pause(browser=None):
    """暂停/恢复浏览器视频。返回 True 表示实际执行了操作。

    Chrome 系用 JS 直控（无视频元素时自动跳过）；
    Firefox 等用 activate + 空格，仅在检测到浏览器有媒体播放时才执行。
    """
    target = browser or _detect_browser()
    if not target:
        return False

    if target in _JS_BROWSERS:
        script = (
            f'tell application "{target}"\n'
            f'  repeat with w in windows\n'
            f'    repeat with t in tabs of w\n'
            f'      execute t javascript "{_VIDEO_JS}"\n'
            f'    end repeat\n'
            f'  end repeat\n'
            f'end tell'
        )
    elif target == "Safari":
        script = (
            f'tell application "Safari"\n'
            f'  repeat with d in documents\n'
            f'    do JavaScript "{_VIDEO_JS}" in d\n'
            f'  end repeat\n'
            f'end tell'
        )
    else:
        # Firefox 等：先检测是否有媒体在播放，没有就不要去抢焦点
        if not _is_browser_playing_media():
            return False
        script = (
            f'tell application "{target}" to activate\n'
            'delay 0.3\n'
            'tell application "System Events" to key code 49'
        )

    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return True
