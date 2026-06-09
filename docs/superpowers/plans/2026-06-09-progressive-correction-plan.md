# 渐进式纠正计划 Implementation Plan（桌面版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 桌面版渐进式纠正计划——阈值从宽松起步，按用户每日表现（连续 3 天良好率≥80%）逐阶段收紧到标准，进阶时鼓励通知，菜单栏显示进度。

**Architecture:** 新增纯逻辑模块 `progression.py`（`ProgressionTracker`：5 阶段阈值表 + 按自然日累计良好率 + 进阶判定 + JSON 持久化）。`core` 把每次 good/bad 喂给 tracker、取阈值改用 `tracker.current_thresholds()`；`tray` 轮询进度更新菜单 + 进阶时弹通知。开关 `progressive_enabled` 默认开。

**Tech Stack:** Python，pytest（`tests/test_*.py`），JSON 持久化（仿 `settings.py`）。

---

## 文件结构

```
sit_monitor/progression.py      — 新：ProgressionTracker（阶段表/进阶判定/持久化），纯逻辑
sit_monitor/paths.py            — 改：加 progression_state_path()
sit_monitor/settings.py         — 改：加 progressive_enabled 字段
sit_monitor/core.py             — 改：建 tracker、喂 record、取阈值、进阶事件
sit_monitor/tray.py             — 改：进度菜单项、开关、进阶通知
sit_monitor/i18n/zh.py, en.py   — 改：阶段/进阶/进度文案
tests/test_progression.py       — 新：ProgressionTracker 单元测试
```

---

## Task 1: ProgressionTracker 核心逻辑（TDD）

**Files:**
- Modify: `sit_monitor/paths.py`
- Create: `sit_monitor/progression.py`
- Test: `tests/test_progression.py`

- [ ] **Step 1: paths.py 加状态文件路径**

在 `sit_monitor/paths.py` 的 `achievements_state_path` 函数后面加：
```python
def progression_state_path() -> str:
    return os.path.join(log_dir(), "progression.json")
```

- [ ] **Step 2: 写失败测试**

`tests/test_progression.py`:
```python
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
    """模拟某一天：先 record 进入该天，再用一段 good + 一段 bad 累计时长。"""
    # 进入该天（建立 last_ts/last_state）
    tracker.record("good", t0, day)
    # 累计 good_sec 秒 good
    tracker.record("good", t0 + good_sec, day)
    # 切到 bad 并累计 bad_sec 秒
    tracker.record("bad", t0 + good_sec, day)
    tracker.record("bad", t0 + good_sec + bad_sec, day)


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
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `python -m pytest tests/test_progression.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sit_monitor.progression'`

- [ ] **Step 4: 写 progression.py**

`sit_monitor/progression.py`:
```python
"""渐进式纠正计划：阈值随每日表现逐阶段收紧。

阶段表 5 级，所有阈值联动（阶段 5 = 现有标准默认）。
表现驱动：连续 3 天良好率≥80% 解锁下一阶段，只升不降。
"""

import json
import os

# 阶段阈值表（索引 0 = 阶段 1）。阶段 5 与 settings 标准默认一致。
STAGE_TABLE = [
    {"shoulder": 16.0, "neck": 30.0, "torso": 12.0, "head_tilt": 18.0},
    {"shoulder": 14.0, "neck": 27.0, "torso": 11.0, "head_tilt": 16.0},
    {"shoulder": 12.0, "neck": 24.0, "torso": 10.0, "head_tilt": 14.0},
    {"shoulder": 11.0, "neck": 22.0, "torso": 9.0, "head_tilt": 13.0},
    {"shoulder": 10.0, "neck": 20.0, "torso": 8.0, "head_tilt": 12.0},
]
MAX_STAGE = 5
GOAL_RATIO = 0.80      # 单日良好率达标线
GOAL_DAYS = 3          # 连续达标天数解锁下一阶段
MAX_DT = 60.0          # 两次 record 间隔超过此值不累计（防暂停/休眠误计）


class ProgressionTracker:
    """按自然日累计良好率、判定进阶。时间与日期由调用方传入（便于测试）。"""

    def __init__(self, path):
        self.path = path
        self.stage = 1
        self.stage_since = None
        self.current_day = None
        self.today_good = 0.0
        self.today_bad = 0.0
        self.recent_days = []       # [{"date":..., "good_ratio":...}]
        self.consecutive_met = 0
        self._last_ts = None
        self._last_state = None
        self._advance_event = None  # 刚进阶到的阶段号，供 UI 弹一次通知
        self._load()

    # ── 阈值 ──
    def current_thresholds(self):
        return dict(STAGE_TABLE[self.stage - 1])

    # ── 记录一次检测 ──
    def record(self, state, now_ts, day_str):
        """state: 'good'/'bad'/'away'(或 None)；now_ts: 秒时间戳；day_str: 'YYYY-MM-DD'。"""
        if self.current_day is None:
            self.current_day = day_str
            if self.stage_since is None:
                self.stage_since = day_str
        elif day_str != self.current_day:
            self._settle_and_advance()
            self.current_day = day_str
            self.today_good = 0.0
            self.today_bad = 0.0
            self._last_ts = None
            self._last_state = None

        if self._last_ts is not None and self._last_state in ("good", "bad"):
            dt = now_ts - self._last_ts
            if 0 < dt < MAX_DT:
                if self._last_state == "good":
                    self.today_good += dt
                else:
                    self.today_bad += dt

        self._last_ts = now_ts
        self._last_state = state if state in ("good", "bad") else None
        self._save()

    def _settle_and_advance(self):
        total = self.today_good + self.today_bad
        if total <= 0:
            return  # 无数据日：跳过，不影响连续序列
        ratio = self.today_good / total
        self.recent_days.append({"date": self.current_day, "good_ratio": round(ratio, 3)})
        self.recent_days = self.recent_days[-30:]
        if ratio >= GOAL_RATIO:
            self.consecutive_met += 1
        else:
            self.consecutive_met = 0
        if self.consecutive_met >= GOAL_DAYS and self.stage < MAX_STAGE:
            self.stage += 1
            self.consecutive_met = 0
            self.stage_since = self.current_day
            self._advance_event = self.stage

    # ── UI 接口 ──
    def progress_summary(self):
        total = self.today_good + self.today_bad
        today_ratio = (self.today_good / total) if total > 0 else 0.0
        return {
            "stage": self.stage,
            "max_stage": MAX_STAGE,
            "today_ratio": today_ratio,
            "consecutive_met": self.consecutive_met,
            "goal_days": GOAL_DAYS,
        }

    def pop_advance_event(self):
        """返回刚进阶到的阶段号（若有），并清除——供调用方只弹一次通知。"""
        ev = self._advance_event
        self._advance_event = None
        return ev

    def set_stage(self, stage):
        self.stage = max(1, min(MAX_STAGE, int(stage)))
        self.consecutive_met = 0
        self._save()

    # ── 持久化 ──
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.stage = int(d.get("stage", 1))
            self.stage_since = d.get("stage_since")
            self.current_day = d.get("current_day")
            self.today_good = float(d.get("today_good", 0.0))
            self.today_bad = float(d.get("today_bad", 0.0))
            self.recent_days = d.get("recent_days", [])
            self.consecutive_met = int(d.get("consecutive_met", 0))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # 文件不存在/损坏 → 保持初始状态（阶段 1）

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({
                    "stage": self.stage,
                    "stage_since": self.stage_since,
                    "current_day": self.current_day,
                    "today_good": round(self.today_good, 1),
                    "today_bad": round(self.today_bad, 1),
                    "recent_days": self.recent_days,
                    "consecutive_met": self.consecutive_met,
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_progression.py -q`
Expected: PASS（11 个测试）

- [ ] **Step 6: 提交**

```bash
git add sit_monitor/progression.py sit_monitor/paths.py tests/test_progression.py
git commit -m "feat: 渐进式纠正计划核心逻辑 ProgressionTracker（阶段表+进阶判定+持久化）"
```

---

## Task 2: settings 开关字段

**Files:**
- Modify: `sit_monitor/settings.py`

- [ ] **Step 1: 加字段**

在 `sit_monitor/settings.py` 的 `Settings` 类中，`stance_mode` 字段行后面加：
```python
    progressive_enabled: bool = True  # 渐进式纠正计划（默认开，从宽松阈值起步）
```

- [ ] **Step 2: 验证 settings 仍可加载（无回归）**

Run: `python -m pytest tests/test_settings.py -q`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add sit_monitor/settings.py
git commit -m "feat: settings 加 progressive_enabled 开关（默认开）"
```

---

## Task 3: i18n 文案

**Files:**
- Modify: `sit_monitor/i18n/zh.py`
- Modify: `sit_monitor/i18n/en.py`

- [ ] **Step 1: zh.py 加文案**

在 `sit_monitor/i18n/zh.py` 的字典中加入（放在 tray.menu 相关条目附近）：
```python
    "tray.menu.progressive": "渐进式计划",
    "tray.menu.stage_adjust": "调整阶段",
    "tray.progress.summary": "纠正计划：阶段 {stage}/{max} · 今日良好率 {ratio}% · 连续达标 {met}/{goal} 天",
    "progression.advance.title": "🎉 进阶啦",
    "progression.advance.msg": "恭喜进入阶段 {stage}！坐姿标准又近了一步",
```

- [ ] **Step 2: en.py 加对应文案**

在 `sit_monitor/i18n/en.py` 的字典中加入：
```python
    "tray.menu.progressive": "Progressive plan",
    "tray.menu.stage_adjust": "Adjust stage",
    "tray.progress.summary": "Plan: stage {stage}/{max} · today {ratio}% good · streak {met}/{goal} days",
    "progression.advance.title": "🎉 Level up",
    "progression.advance.msg": "Welcome to stage {stage}! One step closer to ideal posture",
```

- [ ] **Step 3: 提交**

```bash
git add sit_monitor/i18n/zh.py sit_monitor/i18n/en.py
git commit -m "feat: 渐进式计划 i18n 文案"
```

---

## Task 4: core 集成（建 tracker、喂 record、取阈值）

**Files:**
- Modify: `sit_monitor/core.py`

**Context:** `PostureMonitor.__init__(self, settings, debug=False, on_state_change=None)` 在 `core.py:45`。主循环里 `thresholds = s.thresholds`（约 `core.py:195`），`evaluate_posture(lm, thresholds)`（约 `core.py:400`），good/bad 时 `self.stats.record(...)`（约 `core.py:438-442`）。

- [ ] **Step 1: __init__ 建 progression tracker**

在 `core.py` 顶部 import 区加：
```python
from sit_monitor.progression import ProgressionTracker
from sit_monitor.paths import progression_state_path
```
在 `PostureMonitor.__init__` 末尾（`self.stats = Stats()` 之后）加：
```python
        self.progression = ProgressionTracker(progression_state_path())
```

- [ ] **Step 2: 取阈值改用渐进（若开启）**

把主循环里两处 `thresholds = s.thresholds`（`core.py` 约 133 行 log 前、约 195 行循环内）中**循环内那处**改为：
```python
                if s.progressive_enabled:
                    thresholds = self.progression.current_thresholds()
                else:
                    thresholds = s.thresholds
```
（log_event("start") 那处的 `thresholds = s.thresholds` 保留不变，仅用于日志。）

- [ ] **Step 3: good/bad 时喂给 tracker + 上报进阶**

把 `core.py` 约 437-442 的 good/bad 分支：
```python
                    if is_bad:
                        self.stats.record("bad", now)
                        log_event(self.logger, "bad", reasons=[r for r in reasons], **log_data)
                    else:
                        self.stats.record("good", now)
                        log_event(self.logger, "good", **log_data)
```
改为（在 record 后喂 progression，并在跨天进阶时通过回调上报）：
```python
                    state_str = "bad" if is_bad else "good"
                    self.stats.record(state_str, now)
                    if is_bad:
                        log_event(self.logger, "bad", reasons=[r for r in reasons], **log_data)
                    else:
                        log_event(self.logger, "good", **log_data)
                    if self.settings.progressive_enabled:
                        from datetime import date
                        self.progression.record(state_str, now, date.today().isoformat())
                        adv = self.progression.pop_advance_event()
                        if adv is not None and self.on_state_change:
                            self.on_state_change("stage_up", {"stage": adv})
```

- [ ] **Step 4: away 时也喂 tracker（保持跨天结算）**

找到 `core.py` 约 289 行 `self.stats.record("away", now)`，在其后加：
```python
                    if self.settings.progressive_enabled:
                        from datetime import date
                        self.progression.record("away", now, date.today().isoformat())
```

- [ ] **Step 5: 验证无语法错误 + 现有测试不破**

Run: `python -c "import sit_monitor.core" && python -m pytest tests/test_posture.py tests/test_progression.py -q`
Expected: PASS（import 成功，姿势 + 渐进测试通过）

- [ ] **Step 6: 提交**

```bash
git add sit_monitor/core.py
git commit -m "feat: core 集成渐进计划（取阈值/喂记录/上报进阶）"
```

---

## Task 5: tray 集成（进度菜单、开关、进阶通知）

**Files:**
- Modify: `sit_monitor/tray.py`

**Context:** `tray.py` 用 rumps。`_poll_ui_update(self, _)` 每 0.5s 主线程刷新（已含 `_set_icon`/`_update_stats_menu`）。`_on_state_change(self, state, details)` 接收 core 上报。设置菜单在 `_menu_advanced`/`_menu_simple`。`self.monitor` 是 `PostureMonitor` 实例（含 `.progression`）。

- [ ] **Step 1: 进阶事件 → 通知**

在 `tray.py` 的 `_poll_ui_update` 末尾（`_update_posture_hint` 之后）加进度菜单刷新调用：
```python
        self._update_progress_menu()
```
在 `_on_state_change` 之外不处理 stage_up（它在监控线程）；改为在 `_poll_ui_update` 主线程里轮询 progression 的进阶事件。新增方法：
```python
    def _update_progress_menu(self):
        mon = self.monitor
        if not mon or not getattr(mon, "progression", None) or not self.settings.progressive_enabled:
            if self._mi_progress:
                self._mi_progress.title = ""
            return
        prog = mon.progression
        adv = prog.pop_advance_event()
        if adv is not None:
            rumps.notification(
                t("progression.advance.title"),
                t("progression.advance.msg", stage=adv), "")
        s = prog.progress_summary()
        if self._mi_progress:
            self._mi_progress.title = t(
                "tray.progress.summary",
                stage=s["stage"], max=s["max_stage"],
                ratio=int(s["today_ratio"] * 100),
                met=s["consecutive_met"], goal=s["goal_days"])
```
（注：core Task 4 Step 3 的 `on_state_change("stage_up", ...)` 作为冗余上报保留无害；通知以 tray 主线程 `pop_advance_event` 为准，避免跨线程调 AppKit。移除 core 里的 stage_up 回调亦可——见 Step 4。）

- [ ] **Step 2: __init__ 加菜单项引用**

在 `tray.py` 的 `TrayApp.__init__` 中，其它 `self._mi_*` 引用附近加：
```python
        self._mi_progress = None
```

- [ ] **Step 3: 菜单加进度项 + 开关**

在 `_menu_advanced(self, s)` 构建菜单时（statsmenu/hint 附近）创建并插入进度项与开关：
```python
        self._mi_progress = rumps.MenuItem("")
        self._mi_progressive_toggle = rumps.MenuItem(
            f"{'☑' if s.progressive_enabled else '☐'} {t('tray.menu.progressive')}",
            callback=self._toggle_progressive)
```
把 `self._mi_progress` 加入主菜单（hint 之后），`self._mi_progressive_toggle` 加入设置子菜单（与 `_mi_fatigue` 同级）。新增回调：
```python
    def _toggle_progressive(self, sender):
        self.settings.progressive_enabled = not self.settings.progressive_enabled
        self.settings.save()
        sender.title = (f"{'☑' if self.settings.progressive_enabled else '☐'} "
                        f"{t('tray.menu.progressive')}")
```

- [ ] **Step 4: 移除 core 的冗余 stage_up 回调（避免跨线程通知）**

回到 `sit_monitor/core.py` Task 4 Step 3，把：
```python
                        adv = self.progression.pop_advance_event()
                        if adv is not None and self.on_state_change:
                            self.on_state_change("stage_up", {"stage": adv})
```
改为（不在监控线程 pop，留给 tray 主线程 pop）：
```python
                        # 进阶事件由 tray 主线程 pop_advance_event 处理（避免跨线程调 AppKit）
```

- [ ] **Step 5: 验证 import + 运行**

Run: `python -c "import sit_monitor.tray" && python -m pytest tests/test_progression.py tests/test_settings.py -q`
Expected: PASS

- [ ] **Step 6: 手动测试**

```bash
./service.sh restart   # 或 sit-monitor-service restart（brew 版需同步代码）
```
验证：菜单出现「纠正计划：阶段 1/5 · 今日良好率 X% · 连续达标 0/3 天」；设置菜单有「☑ 渐进式计划」开关；阈值用阶段 1（neck 30，之前卡前倾的 22° 现在判良好）；关闭开关后回固定阈值。

- [ ] **Step 7: 提交**

```bash
git add sit_monitor/core.py sit_monitor/tray.py
git commit -m "feat: tray 渐进计划进度菜单+开关+进阶通知"
```

---

## Self-Review

**Spec 覆盖：**
- 5 阶段阈值表 → Task 1 STAGE_TABLE ✅
- 连续 3 天≥80% 进阶 → Task 1 _settle_and_advance（GOAL_DAYS/GOAL_RATIO）✅
- 只升不降 → Task 1（无降级逻辑）+ test_never_downgrades ✅
- 阶段 5 毕业 → Task 1（stage < MAX_STAGE 才升）+ test_stage_5_graduates ✅
- 每日良好率 + 跨天结算 → Task 1 record/_settle_and_advance + test ✅
- 无数据日跳过 → Task 1（total<=0 return）+ test_no_data_day_skipped ✅
- 持久化 progression.json → Task 1 _load/_save + paths ✅
- 损坏回退 → Task 1 _load except + test_corrupt_file_falls_back ✅
- 手动调阶段 → Task 1 set_stage（菜单入口 Task 5 可后续接，summary 已就绪）✅
- 阈值来源改造（渐进/固定开关）→ Task 4 Step 2 + Task 2 progressive_enabled ✅
- 进阶鼓励通知 → Task 5 _update_progress_menu（主线程 pop）✅
- 菜单进度显示 → Task 5 _mi_progress ✅
- 开关默认开 → Task 2（= True）✅

**类型一致性：** `current_thresholds()` 返回 `{shoulder,neck,torso,head_tilt}` 与
`evaluate_posture` 期望的 `thr["shoulder"]` 等一致 ✅；`progress_summary()` 的 key
（stage/max_stage/today_ratio/consecutive_met/goal_days）与 Task 5 读取一致 ✅；
`record(state, now_ts, day_str)` 签名在 Task 4 调用处一致（传 `date.today().isoformat()`）✅。

**占位符扫描：** 无 TBD/TODO；每个代码 step 均为完整代码 ✅。

**已知简化：** 「调整阶段」菜单项文案已加（i18n stage_adjust），但交互入口（弹窗选阶段）
作为 Task 5 之后的小增强，set_stage 逻辑已就绪、可独立接入，不阻塞主流程。
