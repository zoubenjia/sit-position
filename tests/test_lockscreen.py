from sit_monitor.idle import read_screen_locked
from sit_monitor.health import should_pause_for_lock


def test_read_screen_locked_type():
    # 取得到为 bool；取不到为 None（非 mac / Quartz 异常）
    r = read_screen_locked()
    assert r is None or isinstance(r, bool)


def test_pause_when_locked():
    assert should_pause_for_lock(True) is True


def test_no_pause_when_unlocked():
    assert should_pause_for_lock(False) is False


def test_no_pause_when_unknown():
    # 读不到锁屏状态时绝不能误停监控——宁可多测也不要静默不工作
    assert should_pause_for_lock(None) is False
