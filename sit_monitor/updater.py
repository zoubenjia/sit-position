"""App 自动更新：通过 GitHub Releases API 检查并安装更新（打包模式专用）"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request

log = logging.getLogger(__name__)

GITHUB_API_LATEST = (
    "https://api.github.com/repos/zoubenjia/sit-position/releases/latest"
)


def parse_version(v: str) -> tuple:
    """'v1.3.0' or '1.3.0' -> (1, 3, 0)"""
    return tuple(int(x) for x in v.lstrip("v").split("."))


def check_for_update(current_version: str):
    """检查 GitHub 最新 release，返回 (has_update, tag, release_info)"""
    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "SitMonitor"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        release = json.loads(resp.read())
    tag = release.get("tag_name", "")
    try:
        remote = parse_version(tag)
        local = parse_version(current_version)
        return remote > local, tag, release
    except (ValueError, IndexError):
        return False, tag, release


def get_dmg_url(release: dict) -> str | None:
    """从 release assets 中找 macOS DMG 下载链接"""
    for asset in release.get("assets", []):
        if asset["name"].endswith(".dmg"):
            return asset["browser_download_url"]
    return None


def download_update(url: str, progress_cb=None) -> str:
    """下载 DMG 到临时目录，返回本地路径"""
    tmp_dir = tempfile.mkdtemp(prefix="sitmonitor_update_")
    dmg_path = os.path.join(tmp_dir, "SitMonitor-update.dmg")

    req = urllib.request.Request(url, headers={"User-Agent": "SitMonitor"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dmg_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded, total)
    return dmg_path


def get_app_path() -> str | None:
    """获取当前运行的 .app bundle 路径"""
    if not getattr(sys, "frozen", False):
        return None
    exe = sys.executable
    # /path/to/SitMonitor.app/Contents/MacOS/SitMonitor
    parts = exe.split(os.sep)
    for i, p in enumerate(parts):
        if p.endswith(".app"):
            return os.sep.join(parts[: i + 1])
    return None


def install_and_restart(dmg_path: str) -> bool:
    """创建更新脚本，退出当前 app，脚本接管完成替换和重启"""
    app_path = get_app_path()
    if not app_path:
        return False

    pid = os.getpid()
    tmp_dir = os.path.dirname(dmg_path)
    script_path = os.path.join(tmp_dir, "sit_update.sh")

    script = f"""#!/bin/bash
# SitMonitor auto-update script
set -e

# 等待当前进程退出（最多 30 秒）
for i in $(seq 1 60); do
    kill -0 {pid} 2>/dev/null || break
    sleep 0.5
done

# 挂载 DMG
MOUNT_OUT=$(hdiutil attach "{dmg_path}" -nobrowse -noautoopen 2>&1)
MOUNT_POINT=$(echo "$MOUNT_OUT" | grep -oE '/Volumes/[^[:space:]]+' | head -1)
if [ -z "$MOUNT_POINT" ]; then
    MOUNT_POINT="/Volumes/SitMonitor"
fi

# 查找新 .app
NEW_APP="$MOUNT_POINT/SitMonitor.app"
if [ ! -d "$NEW_APP" ]; then
    hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
    osascript -e 'display notification "Update failed: app not found in DMG" with title "Sit Monitor"'
    exit 1
fi

# 替换旧 app
rm -rf "{app_path}"
cp -R "$NEW_APP" "{app_path}"

# 卸载 DMG 并清理
hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
rm -rf "{tmp_dir}"

# 重新启动
open "{app_path}"
"""

    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, 0o755)

    # 后台启动更新脚本
    subprocess.Popen(
        ["/bin/bash", script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True
