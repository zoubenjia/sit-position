"""轻量 i18n 模块：t() 翻译函数 + 语言切换"""

import importlib
import logging

log = logging.getLogger(__name__)

_strings: dict[str, str] = {}
_fallback: dict[str, str] = {}
_current_lang: str = "zh"
_initialized: bool = False


def _load_lang(lang: str) -> dict[str, str]:
    """动态加载语言模块"""
    try:
        mod = importlib.import_module(f"sit_monitor.i18n.{lang}")
        return dict(mod.STRINGS)
    except (ImportError, AttributeError):
        log.warning("i18n: language module '%s' not found", lang)
        return {}


def set_language(lang: str) -> None:
    """切换语言。加载对应模块，zh 始终作为 fallback。"""
    global _strings, _fallback, _current_lang, _initialized
    _current_lang = lang
    _initialized = True
    if lang == "zh":
        _strings = _load_lang("zh")
        _fallback = _strings
    else:
        _fallback = _load_lang("zh")
        _strings = _load_lang(lang)


def get_language() -> str:
    """返回当前语言代码"""
    _ensure_init()
    return _current_lang


def _ensure_init() -> None:
    """首次调用时自动从设置初始化"""
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        from sit_monitor.settings import Settings
        lang = Settings.load().language
    except Exception:
        lang = "zh"
    set_language(lang)


def t(key: str, **kwargs) -> str:
    """查找本地化字符串。

    回退链：当前语言 -> zh -> 原始 key。
    支持 .format(**kwargs) 参数替换。
    """
    _ensure_init()
    template = _strings.get(key) or _fallback.get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return template
    return template
