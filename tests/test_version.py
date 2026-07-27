import os
import tomllib

from sit_monitor.version import get_version, __version__


def _pyproject_version():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_version_matches_pyproject():
    # 源码模式下版本必须来自 pyproject，杜绝手写常量漂移
    assert get_version() == _pyproject_version()


def test_module_attr_matches():
    assert __version__ == get_version()


def test_version_is_nonempty_string():
    v = get_version()
    assert isinstance(v, str) and v.strip()


def test_tray_version_matches_pyproject():
    # tray 展示/更新检查用的 VERSION 必须与 pyproject 一致（v1.5.3 曾漏改导致反复提示重启）
    from sit_monitor.tray import VERSION
    assert VERSION == _pyproject_version()
