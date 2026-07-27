"""单一版本来源。

历史教训：版本号同时写在 pyproject.toml 和 tray.py 的 VERSION 常量里，
v1.5.3 发版漏改后者 → 运行中报 1.5.2、磁盘是 1.5.3 → app 反复弹
「代码已更新，正在重启」。这里统一出口，杜绝漂移。

解析顺序（先源码后安装，因为开发时 pyproject 才是权威；已安装包的
元数据可能陈旧——项目 venv 的 egg-info 就曾停在 1.4.0）：
1. 源码同级的 pyproject.toml（开发/源码运行）
2. 已安装包元数据（brew/pip 安装）
3. 回退常量（PyInstaller 打包，两者都不可用）
"""

import os

# 打包模式的兜底值；发版时随 pyproject 一起更新。
_FALLBACK_VERSION = "1.5.3"


def get_version():
    """返回当前版本号字符串。"""
    # 1. 源码模式：包目录的上一级即项目根
    try:
        import tomllib
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "pyproject.toml"), "rb") as f:
            v = tomllib.load(f)["project"]["version"]
        if v:
            return str(v)
    except Exception:
        pass

    # 2. 安装模式：包元数据
    try:
        from importlib.metadata import version as _pkg_version
        v = _pkg_version("sit-monitor")
        if v:
            return str(v)
    except Exception:
        pass

    return _FALLBACK_VERSION


__version__ = get_version()
