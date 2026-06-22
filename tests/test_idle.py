from sit_monitor.idle import (
    read_input_idle_seconds,
    deep_sleep_decision,
    ENTER_IDLE_SECONDS,
    WAKE_IDLE_SECONDS,
)


def test_read_input_idle_seconds_type():
    # 取得到则为非负 float；取不到为 None（非 mac / API 失败）
    r = read_input_idle_seconds()
    assert r is None or (isinstance(r, float) and r >= 0)


# ── 进入：仅当未休眠 + away + 空闲达门槛 ──
def test_enter_when_away_and_idle_enough():
    assert deep_sleep_decision(False, True, ENTER_IDLE_SECONDS) == "enter"


def test_no_enter_when_idle_below_threshold():
    assert deep_sleep_decision(False, True, ENTER_IDLE_SECONDS - 1) == "none"


def test_no_enter_when_not_away():
    assert deep_sleep_decision(False, False, ENTER_IDLE_SECONDS + 999) == "none"


def test_no_enter_when_idle_unavailable():
    assert deep_sleep_decision(False, True, None) == "none"


# ── 休眠中：键鼠活动→wake；空闲不可读→failsafe wake；仍空闲→stay ──
def test_wake_on_input_activity():
    assert deep_sleep_decision(True, False, WAKE_IDLE_SECONDS - 1) == "wake"


def test_wake_failsafe_when_idle_unavailable_in_sleep():
    assert deep_sleep_decision(True, False, None) == "wake"


def test_stay_when_still_idle():
    assert deep_sleep_decision(True, False, 400.0) == "stay_sleep"


def test_stay_when_idle_equals_wake_threshold():
    # 唤醒条件是严格 < WAKE_IDLE_SECONDS；等值不唤醒
    assert deep_sleep_decision(True, False, WAKE_IDLE_SECONDS) == "stay_sleep"
