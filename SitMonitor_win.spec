# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SitMonitor.exe (Windows)"""

import os
import sys

block_cipher = None
ROOT = os.path.abspath(".")

# ML 模型文件
datas = [
    (os.path.join(ROOT, "pose_landmarker_lite.task"), "models"),
    (os.path.join(ROOT, "face_landmarker.task"), "models"),
    (os.path.join(ROOT, "sit_monitor", "assets"), "assets"),
    (os.path.join(ROOT, "sit_monitor", "i18n"), "sit_monitor/i18n"),
]

# cloud_config.json 可选
cloud_cfg = os.path.join(ROOT, "cloud_config.json")
if os.path.exists(cloud_cfg):
    datas.append((cloud_cfg, "."))

# 排除 macOS 专用模块
excludes = [
    "sit_monitor.tray",
    "sit_monitor.platform_mac",
    "rumps",
    "sit_monitor.mcp_server",
]

# 图标路径（可选）
ico_path = os.path.join(ROOT, "build-resources", "SitMonitor.ico")
icon_arg = ico_path if os.path.exists(ico_path) else None

a = Analysis(
    [os.path.join(ROOT, "sit_monitor", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pystray",
        "winotify",
        "pyttsx3",
        "cv2",
        "mediapipe",
        "numpy",
        "httpx",
        "PIL",
        "PIL.Image",
        "sit_monitor.core",
        "sit_monitor.tray_win",
        "sit_monitor.paths",
        "sit_monitor.settings",
        "sit_monitor.report",
        "sit_monitor.posture",
        "sit_monitor.stats",
        "sit_monitor.debug",
        "sit_monitor.tts",
        "sit_monitor.platform",
        "sit_monitor.platform_win",
        "sit_monitor.icon_gen",
        "sit_monitor.i18n",
        "sit_monitor.exercise",
        "sit_monitor.exercise.base",
        "sit_monitor.exercise.pushup",
        "sit_monitor.exercise.voice_coach",
        "sit_monitor.cloud",
        "sit_monitor.cloud.client",
        "sit_monitor.cloud.models",
        "sit_monitor.cloud.achievements",
        "sit_monitor.cloud.sync",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SitMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # 无控制台窗口（托盘应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=icon_arg,
    version_info=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SitMonitor",
)
