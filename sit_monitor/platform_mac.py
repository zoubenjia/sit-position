"""macOS 平台相关：通知、TTS、媒体控制"""

import subprocess

# --------------- 通知 ---------------

def send_notification(title, message, sound=False, use_notification_center=False):
    """发送通知。返回 say 进程（如有），供调用方跟踪和终止。"""
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
    safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')

    if use_notification_center:
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
    else:
        script = (
            f'display dialog "{safe_msg}" with title "{safe_title}" '
            f'buttons {{"好的"}} default button 1 giving up after 10'
        )
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if sound:
        speech = message.replace("\n", "，")
        return subprocess.Popen(["say", "-v", "Tingting", speech], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def media_play_pause(browser=None):
    """暂停/恢复浏览器视频。Chrome 系用 JS 直控，其他用空格键。"""
    target = browser or _detect_browser()
    if not target:
        return

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
        script = (
            f'tell application "{target}" to activate\n'
            'delay 0.3\n'
            'tell application "System Events" to key code 49'
        )

    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
