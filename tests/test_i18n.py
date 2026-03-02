"""i18n 模块测试"""

import importlib

import pytest


@pytest.fixture(autouse=True)
def reset_i18n():
    """每个测试前重置 i18n 状态"""
    import sit_monitor.i18n as i18n_mod
    i18n_mod._strings = {}
    i18n_mod._fallback = {}
    i18n_mod._current_lang = "zh"
    i18n_mod._initialized = False
    yield
    i18n_mod._initialized = False


def test_set_language_zh():
    from sit_monitor.i18n import set_language, get_language, t
    set_language("zh")
    assert get_language() == "zh"
    assert t("posture.head_forward").startswith("头太靠前")


def test_set_language_en():
    from sit_monitor.i18n import set_language, get_language, t
    set_language("en")
    assert get_language() == "en"
    assert t("posture.head_forward").startswith("Head too far forward")


def test_fallback_to_zh():
    """en 中缺少的 key 应回退到 zh"""
    from sit_monitor.i18n import set_language, t
    # 先确保 en 模块正常
    set_language("en")
    # 所有 zh key 在 en 中也应存在；如果删除一个 en key，应回退
    import sit_monitor.i18n as mod
    # 手动删除一个 en key 来测试 fallback
    mod._strings.pop("core.exited", None)
    assert t("core.exited") == "已退出。"


def test_fallback_to_key():
    """zh 和 en 都没有的 key 应返回 key 本身"""
    from sit_monitor.i18n import set_language, t
    set_language("zh")
    assert t("nonexistent.key") == "nonexistent.key"


def test_format_params():
    from sit_monitor.i18n import set_language, t
    set_language("zh")
    result = t("core.sit_alert_msg", minutes=45)
    assert "45" in result
    assert "分钟" in result


def test_format_params_en():
    from sit_monitor.i18n import set_language, t
    set_language("en")
    result = t("core.sit_alert_msg", minutes=45)
    assert "45" in result
    assert "minutes" in result


def test_format_missing_param():
    """缺少参数时不应崩溃，返回模板原文"""
    from sit_monitor.i18n import set_language, t
    set_language("zh")
    result = t("core.sit_alert_msg")  # 缺少 minutes
    assert "{minutes" in result or "分钟" in result


def test_language_switch():
    """切换语言后字符串应立即改变"""
    from sit_monitor.i18n import set_language, t
    set_language("zh")
    zh_text = t("core.exited")
    set_language("en")
    en_text = t("core.exited")
    assert zh_text != en_text
    assert zh_text == "已退出。"
    assert en_text == "Exited."


def test_unknown_language_fallback():
    """不存在的语言应回退到 zh"""
    from sit_monitor.i18n import set_language, t
    set_language("fr")
    # _strings 为空，应回退到 _fallback (zh)
    assert t("core.exited") == "已退出。"


def test_all_zh_keys_in_en():
    """确保 en.py 覆盖了 zh.py 的所有 key"""
    from sit_monitor.i18n.zh import STRINGS as zh
    from sit_monitor.i18n.en import STRINGS as en
    missing = set(zh.keys()) - set(en.keys())
    assert not missing, f"en.py missing keys: {missing}"


def test_all_en_keys_in_zh():
    """确保 zh.py 覆盖了 en.py 的所有 key（不应有只存在于 en 的 key）"""
    from sit_monitor.i18n.zh import STRINGS as zh
    from sit_monitor.i18n.en import STRINGS as en
    extra = set(en.keys()) - set(zh.keys())
    assert not extra, f"en.py has extra keys not in zh.py: {extra}"


def test_auto_init_from_settings(tmp_path, monkeypatch):
    """自动从 settings.json 初始化语言"""
    import json
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"language": "en"}))

    import sit_monitor.settings as settings_mod
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", str(settings_file))

    from sit_monitor.i18n import t
    # 自动初始化应读取 settings 中的 language=en
    result = t("core.exited")
    assert result == "Exited."


def test_tts_voice_per_language():
    """验证 TTS 语音配置"""
    from sit_monitor.i18n import set_language, t
    set_language("zh")
    assert t("platform.tts_voice") == "Tingting"
    set_language("en")
    assert t("platform.tts_voice") == "Samantha"
