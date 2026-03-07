"""统一路径解析：开发模式 vs PyInstaller 打包模式"""

import os
import sys


def is_bundled() -> bool:
    """是否在 PyInstaller 打包环境中运行"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _bundle_dir() -> str:
    """PyInstaller 解包后的只读资源目录"""
    return sys._MEIPASS  # type: ignore[attr-defined]


def _dev_root() -> str:
    """开发模式下的项目根目录（sit-position/）
    支持 SITMONITOR_DATA_DIR 环境变量（Homebrew 安装用）"""
    env_dir = os.environ.get("SITMONITOR_DATA_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data_dir() -> str:
    """可写数据目录：打包模式用 ~/Library/Application Support/SitMonitor/"""
    if is_bundled():
        d = os.path.join(os.path.expanduser("~"), "Library",
                         "Application Support", "SitMonitor")
        os.makedirs(d, exist_ok=True)
        return d
    return _dev_root()


# ── 只读资源 ──

def model_path() -> str:
    base = _bundle_dir() if is_bundled() else _dev_root()
    return os.path.join(base, "models", "pose_landmarker_lite.task") if is_bundled() \
        else os.path.join(base, "pose_landmarker_lite.task")


def face_model_path() -> str:
    base = _bundle_dir() if is_bundled() else _dev_root()
    return os.path.join(base, "models", "face_landmarker.task") if is_bundled() \
        else os.path.join(base, "face_landmarker.task")


def assets_dir() -> str:
    if is_bundled():
        return os.path.join(_bundle_dir(), "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def cloud_config_path() -> str:
    if is_bundled():
        return os.path.join(_bundle_dir(), "cloud_config.json")
    return os.path.join(_dev_root(), "cloud_config.json")


# ── 可写数据 ──

def log_dir() -> str:
    d = os.path.join(_data_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def settings_path() -> str:
    return os.path.join(_data_dir(), "settings.json")


def achievements_state_path() -> str:
    return os.path.join(log_dir(), "achievements.json")


def sync_state_path() -> str:
    return os.path.join(log_dir(), "sync_state.json")


# ── 运行时 ──

def python_executable() -> str:
    """返回当前 Python 解释器路径"""
    if is_bundled():
        return sys.executable
    venv_python = os.path.join(_dev_root(), ".venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def project_dir() -> str:
    """项目根目录（打包模式下无意义，仅开发模式使用）"""
    return _dev_root()
