import os
import tempfile
import pytest
from sit_monitor.progression import ProgressionTracker, STAGE_TABLE, MAX_STAGE


@pytest.fixture
def tmp_path_file():
    fd, p = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(p)  # 让文件初始不存在
    yield p
    if os.path.exists(p):
        os.unlink(p)


def feed_day(tracker, day, good_sec, bad_sec, t0=0.0):
    """模拟某一天：先 record 进入该天，再用一段 good + 一段 bad 累计时长。

    用小步长（≤ MAX_DT）累计，贴近真实轮询（每 1-2s 一次 record）；
    单次大间隔会被 MAX_DT 当作休眠/暂停丢弃，不能用来模拟时长。
    """
    STEP = 10.0  # < MAX_DT(60)，保证每段都被累计
    t = t0
    tracker.record("good", t, day)  # 进入该天，建立 last_ts/last_state
    remaining = good_sec
    while remaining > 0:
        step = min(STEP, remaining)
        t += step
        tracker.record("good", t, day)
        remaining -= step
    tracker.record("bad", t, day)   # 切到 bad（dt=0 不累计，仅置 last_state）
    remaining = bad_sec
    while remaining > 0:
        step = min(STEP, remaining)
        t += step
        tracker.record("bad", t, day)
        remaining -= step


def test_initial_stage_is_1(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    assert tr.stage == 1


def test_current_thresholds_matches_stage(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    assert tr.current_thresholds() == STAGE_TABLE[0]
    tr.set_stage(3)
    assert tr.current_thresholds() == STAGE_TABLE[2]


def test_three_good_days_advances_stage(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    # 3 天，每天 good 90s / bad 10s → 良好率 90% ≥ 80%
    feed_day(tr, "2026-01-01", 90, 10)
    feed_day(tr, "2026-01-02", 90, 10)   # 跨天结算 01-01（达标，连续=1）
    feed_day(tr, "2026-01-03", 90, 10)   # 结算 01-02（连续=2）
    feed_day(tr, "2026-01-04", 90, 10)   # 结算 01-03（连续=3 → 进阶到 2）
    assert tr.stage == 2


def test_bad_day_resets_streak(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    feed_day(tr, "2026-01-01", 90, 10)   # 达标
    feed_day(tr, "2026-01-02", 50, 50)   # 结算 01-01（连续=1）
    feed_day(tr, "2026-01-03", 90, 10)   # 结算 01-02（50% 未达标 → 连续=0）
    feed_day(tr, "2026-01-04", 90, 10)   # 结算 01-03（连续=1）
    assert tr.stage == 1   # 不足连续 3 天，未进阶


def test_never_downgrades(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    tr.set_stage(3)
    feed_day(tr, "2026-01-01", 10, 90)   # 差表现
    feed_day(tr, "2026-01-02", 10, 90)   # 结算 01-01（未达标）
    assert tr.stage == 3   # 只升不降


def test_no_data_day_skipped(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    feed_day(tr, "2026-01-01", 90, 10)
    # 01-02 无数据：直接跳到 01-03 喂数据，01-02 不结算（无 good/bad）
    feed_day(tr, "2026-01-03", 90, 10)   # 结算 01-01（连续=1）
    feed_day(tr, "2026-01-04", 90, 10)   # 结算 01-03（连续=2）
    assert tr.consecutive_met == 2       # 无数据日没打断也没计入


def test_stage_5_graduates(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    tr.set_stage(MAX_STAGE)
    for i in range(1, 6):
        feed_day(tr, f"2026-02-0{i}", 100, 0)  # 全达标
    assert tr.stage == MAX_STAGE   # 封顶不再进阶


def test_advance_event_popped_once(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    feed_day(tr, "2026-01-01", 100, 0)
    feed_day(tr, "2026-01-02", 100, 0)
    feed_day(tr, "2026-01-03", 100, 0)
    feed_day(tr, "2026-01-04", 100, 0)   # 进阶到 2
    assert tr.pop_advance_event() == 2
    assert tr.pop_advance_event() is None  # 只弹一次


def test_persistence_roundtrip(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    tr.set_stage(3)
    feed_day(tr, "2026-01-01", 90, 10)
    tr2 = ProgressionTracker(tmp_path_file)  # 重新加载
    assert tr2.stage == 3


def test_corrupt_file_falls_back(tmp_path_file):
    with open(tmp_path_file, "w") as f:
        f.write("{not json")
    tr = ProgressionTracker(tmp_path_file)
    assert tr.stage == 1   # 回退初始


def test_progress_summary_shape(tmp_path_file):
    tr = ProgressionTracker(tmp_path_file)
    tr.record("good", 0.0, "2026-01-01")
    tr.record("good", 30.0, "2026-01-01")
    s = tr.progress_summary()
    assert s["stage"] == 1
    assert s["max_stage"] == MAX_STAGE
    assert s["goal_days"] == 3
    assert 0.0 <= s["today_ratio"] <= 1.0
