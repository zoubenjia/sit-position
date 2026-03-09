# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SitMonitor.app"""

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

# 排除不需要的模块
excludes = [
    "sit_monitor.tray_win",
    "sit_monitor.platform_win",
    "pystray",
    "sit_monitor.mcp_server",
    "tkinter",
]

a = Analysis(
    [os.path.join(ROOT, "sit_monitor", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "rumps",
        "cv2",
        "mediapipe",
        "numpy",
        "httpx",
        "sit_monitor.core",
        "sit_monitor.tray",
        "sit_monitor.paths",
        "sit_monitor.settings",
        "sit_monitor.report",
        "sit_monitor.posture",
        "sit_monitor.stats",
        "sit_monitor.debug",
        "sit_monitor.tts",
        "sit_monitor.platform",
        "sit_monitor.platform_mac",
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SitMonitor",
)

# 图标路径（可选）
icns_path = os.path.join(ROOT, "build-resources", "SitMonitor.icns")
icon_arg = icns_path if os.path.exists(icns_path) else None

app = BUNDLE(
    coll,
    name="SitMonitor.app",
    icon=icon_arg,
    bundle_identifier="com.zoubenjia.sitmonitor",
    info_plist={
        "LSUIElement": True,                      # 不在 Dock 显示
        "CFBundleName": "SitMonitor",
        "CFBundleDisplayName": "Sit Monitor",
        "CFBundleVersion": "1.3.0",
        "CFBundleShortVersionString": "1.3.0",
        "NSCameraUsageDescription": "Sit Monitor 需要摄像头来检测您的坐姿。",
        "NSMicrophoneUsageDescription": "Sit Monitor 需要检测通话状态以静音语音播报。",
        "NSHighResolutionCapable": True,
    },
)
