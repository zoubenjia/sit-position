import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from eval_deep_sleep import summarize


def _events():
    return [
        {"event": "deep_sleep_enter", "idle_seconds": 300.0},
        {"event": "deep_sleep_exit", "duration_s": 1200.0},
        {"event": "deep_sleep_enter", "idle_seconds": 305.0},
        {"event": "deep_sleep_exit", "duration_s": 20.0},     # <30s：疑似睡早
    ]


def test_counts_sessions_and_durations():
    r = summarize(_events(), {})
    assert r["sessions"] == 2
    assert r["total_sleep_seconds"] == 1220.0          # 1200 + 20


def test_short_exits_flagged():
    r = summarize(_events(), {})
    assert r["short_exits"] == 1                        # 仅 20s 那次


def test_empty_events():
    r = summarize([], {})
    assert r["sessions"] == 0
    assert r["total_sleep_seconds"] == 0.0
    assert r["short_exits"] == 0
