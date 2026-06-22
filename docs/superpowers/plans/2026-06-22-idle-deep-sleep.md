# 输入空闲 + 摄像头确认的深度休眠 Implementation Plan（桌面版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 人真不在（摄像头判定 away 且键鼠空闲≥5 分钟）时进入深度休眠——关摄像头、每 5 分钟瞄一次、碰键鼠或瞄到人即唤醒——并埋点以便事后评估省电/漏检效果。

**Architecture:** 新增纯逻辑模块 `idle.py`（读系统空闲秒数 + 三态决策函数，可单测，不依赖真摄像头/真键鼠）。`core.py` 主循环顶部接入决策、按结果进入/维持/瞄帧/唤醒，并把状态转移事件写入独立的 `deepsleep_events.jsonl`（复用现有 `log_event`）。离线脚本 `scripts/eval_deep_sleep.py` 读日志聚合评估报告。

**Tech Stack:** Python，pytest（`tests/test_*.py`），Quartz（`CGEventSourceSecondsSinceLastEventType`，macOS 专有，失败回退），RotatingFileHandler JSON 日志。

## Global Constraints

- 系统空闲读取失败（非 mac / Quartz 异常）→ `read_input_idle_seconds()` 返回 `None`，整套深度休眠**退回现有行为**，不影响其它平台。
- 参数为模块常量（本期不提为 Settings）：`ENTER_IDLE_SECONDS=300.0`、`CAM_PEEK_INTERVAL_SECONDS=300.0`、`WAKE_IDLE_SECONDS=5.0`、`DEEP_SLEEP_POLL_SECONDS=2.0`。
- 深度休眠期**不喂 `progression`**（away 本就不计良好率）。
- 菜单栏状态沿用现有 away/人不在显示，不新增图标。
- 提交信息结尾：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 测试用项目 venv：`source .venv/bin/activate` 后跑 `python -m pytest`。

---

## 文件结构

```
sit_monitor/idle.py            — 新：read_input_idle_seconds() + deep_sleep_decision()（纯逻辑）
tests/test_idle.py             — 新：idle.py 单元测试
sit_monitor/core.py            — 改：事件日志器 + 主循环接入深度休眠三态
scripts/eval_deep_sleep.py     — 新：离线评估（summarize 纯函数 + CLI）
tests/test_eval_deep_sleep.py  — 新：summarize 单元测试
```

---

## Task 1: idle.py 纯逻辑（系统空闲读取 + 三态决策）

**Files:**
- Create: `sit_monitor/idle.py`
- Test: `tests/test_idle.py`

**Interfaces:**
- Produces:
  - `read_input_idle_seconds() -> float | None` — 自上次键鼠输入的秒数；取不到返回 `None`。
  - `deep_sleep_decision(in_deep_sleep: bool, is_away: bool, idle_seconds: float | None, secs_since_peek: float) -> str` — 返回 `"enter"` / `"wake"` / `"peek_camera"` / `"stay_sleep"` / `"none"`。
  - 模块常量 `ENTER_IDLE_SECONDS`、`CAM_PEEK_INTERVAL_SECONDS`、`WAKE_IDLE_SECONDS`、`DEEP_SLEEP_POLL_SECONDS`。

- [ ] **Step 1: 写失败测试**

`tests/test_idle.py`:
```python
from sit_monitor.idle import (
    read_input_idle_seconds,
    deep_sleep_decision,
    ENTER_IDLE_SECONDS,
    CAM_PEEK_INTERVAL_SECONDS,
    WAKE_IDLE_SECONDS,
)


def test_read_input_idle_seconds_type():
    # 取得到则为非负 float；取不到为 None（非 mac / API 失败）
    r = read_input_idle_seconds()
    assert r is None or (isinstance(r, float) and r >= 0)


# ── 进入：仅当未休眠 + away + 空闲达门槛 ──
def test_enter_when_away_and_idle_enough():
    assert deep_sleep_decision(False, True, ENTER_IDLE_SECONDS, 0) == "enter"


def test_no_enter_when_idle_below_threshold():
    assert deep_sleep_decision(False, True, ENTER_IDLE_SECONDS - 1, 0) == "none"


def test_no_enter_when_not_away():
    assert deep_sleep_decision(False, False, ENTER_IDLE_SECONDS + 999, 0) == "none"


def test_no_enter_when_idle_unavailable():
    assert deep_sleep_decision(False, True, None, 0) == "none"


# ── 休眠中：键鼠活动→wake；空闲不可读→failsafe wake ──
def test_wake_on_input_activity():
    assert deep_sleep_decision(True, False, WAKE_IDLE_SECONDS - 1, 10) == "wake"


def test_wake_failsafe_when_idle_unavailable_in_sleep():
    assert deep_sleep_decision(True, False, None, 10) == "wake"


# ── 休眠中且仍空闲：到兜底间隔→peek，否则 stay ──
def test_peek_when_interval_elapsed():
    assert deep_sleep_decision(True, False, 400.0, CAM_PEEK_INTERVAL_SECONDS) == "peek_camera"


def test_stay_when_interval_not_elapsed():
    assert deep_sleep_decision(True, False, 400.0, CAM_PEEK_INTERVAL_SECONDS - 1) == "stay_sleep"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/test_idle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sit_monitor.idle'`

- [ ] **Step 3: 写 idle.py**

`sit_monitor/idle.py`:
```python
"""系统输入空闲读取 + 深度休眠三态决策（纯逻辑，可单测）。

人真不在（摄像头 away 且键鼠长时间空闲）时进入深度休眠：关摄像头、
仅极低频轮询空闲秒数、每若干分钟开摄像头瞄一眼；碰键鼠或瞄到人即唤醒。
"""

# 参数（本期为模块常量，未提为 Settings）。
ENTER_IDLE_SECONDS = 300.0       # 进入深度休眠的键鼠空闲门槛（且须同时 away）
CAM_PEEK_INTERVAL_SECONDS = 300.0  # 休眠期摄像头兜底瞄一眼的间隔
WAKE_IDLE_SECONDS = 5.0          # 空闲秒数低于此值＝刚有键鼠输入＝唤醒
DEEP_SLEEP_POLL_SECONDS = 2.0    # 休眠期轻量轮询周期


def read_input_idle_seconds():
    """返回自上次任意键鼠输入以来的秒数；取不到（非 mac / Quartz 异常）返回 None。"""
    try:
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateHIDSystemState,
        )
        try:
            from Quartz import kCGAnyInputEventType
        except ImportError:
            kCGAnyInputEventType = 0xFFFFFFFF  # ~0：任意输入事件
        return float(CGEventSourceSecondsSinceLastEventType(
            kCGEventSourceStateHIDSystemState, kCGAnyInputEventType))
    except Exception:
        return None


def deep_sleep_decision(in_deep_sleep, is_away, idle_seconds, secs_since_peek):
    """根据当前状态与信号决定动作。

    in_deep_sleep: 当前是否已处于深度休眠
    is_away:       最近一次摄像头检测是否判定无人（仅用于"进入"判定）
    idle_seconds:  键鼠空闲秒数；None＝取不到（feature 不可用）
    secs_since_peek: 距上次摄像头瞄一眼的秒数（仅休眠中有意义）

    返回 "enter" / "wake" / "peek_camera" / "stay_sleep" / "none"。
    """
    if not in_deep_sleep:
        if idle_seconds is None:
            return "none"  # 取不到空闲 → 永不进入，退回现有行为
        if is_away and idle_seconds >= ENTER_IDLE_SECONDS:
            return "enter"
        return "none"

    # 已在深度休眠
    if idle_seconds is None:
        return "wake"  # failsafe：信号不可用就唤醒回正常检测
    if idle_seconds < WAKE_IDLE_SECONDS:
        return "wake"  # 刚有键鼠输入
    if secs_since_peek >= CAM_PEEK_INTERVAL_SECONDS:
        return "peek_camera"
    return "stay_sleep"
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/test_idle.py -q`
Expected: PASS（9 个测试）

- [ ] **Step 5: 提交**

```bash
git add sit_monitor/idle.py tests/test_idle.py
git commit -m "feat: 深度休眠纯逻辑 idle.py（系统空闲读取 + 三态决策）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: core.py 接入深度休眠 + 事件埋点

**Files:**
- Modify: `sit_monitor/core.py`

**Interfaces:**
- Consumes: `idle.read_input_idle_seconds`, `idle.deep_sleep_decision`, 常量 `DEEP_SLEEP_POLL_SECONDS`；现有 `log_event(logger, event_type, **kwargs)`、`self._open_camera`、`self._sleep`、`self.logger`。
- Produces: 写 `deepsleep_events.jsonl`，事件 `deep_sleep_enter` / `camera_peek` / `deep_sleep_exit` / `away_idle_snapshot`（字段见 spec）。

**Context:** 主循环在 `core.py:231` 的 `while self.running:`。`now = time.time()` 在 `core.py:232`。节流/间隔块在 `core.py:239-267`。away 分支（`if not person_present:`）在 `core.py:323`，其中 `self.stats.record("away", now)` 在 `core.py:347`。`person_present` 在 `core.py:299-315` 计算。`setup_logging()` 在 `core.py:32`。

- [ ] **Step 1: 加事件日志器**

在 `core.py` 的 `setup_logging()` 函数（`core.py:32-42`）后面新增（紧接其后）：
```python
def setup_event_logging():
    """深度休眠事件单独写 deepsleep_events.jsonl，与 posture.jsonl 同目录、同轮转策略。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("deepsleep")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "deepsleep_events.jsonl"),
            maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger
```

- [ ] **Step 2: import idle 模块**

把 `core.py:25` 的：
```python
from sit_monitor.progression import ProgressionTracker
```
改为（其后追加一行）：
```python
from sit_monitor.progression import ProgressionTracker
from sit_monitor.idle import read_input_idle_seconds, deep_sleep_decision, DEEP_SLEEP_POLL_SECONDS
```

- [ ] **Step 3: __init__ 建事件日志器**

在 `core.py:69` 的 `self.progression = ProgressionTracker(progression_state_path())` 后面加：
```python
        self.event_logger = setup_event_logging()
```

- [ ] **Step 4: run() 初始化深度休眠状态变量**

在 `core.py:220` 的 `camera_retry_interval = 5` 后面加（与其它循环状态变量同处）：
```python
        # --- 深度休眠：away 且键鼠长时间空闲时关摄像头、降到每 5 分钟瞄一眼 ---
        deep_sleep = False
        deep_sleep_start = 0.0     # 本次休眠进入时刻
        last_cam_peek = 0.0        # 上次摄像头兜底瞄一眼时刻
        peek_count = 0             # 本次休眠累计瞄帧次数
        peeking = False            # 本轮是否为兜底瞄帧（检测后据结果决定去留）
        currently_away = False     # 最近一次检测是否判定无人（供进入判定）
        away_idle_logged = False   # 本次 away 是否已记 away_idle_snapshot
```

- [ ] **Step 5: 循环顶部接入休眠处理（写失败前先放代码）**

在 `core.py:232` 的 `now = time.time()` 之后、`# 运行中实时读取设置` 之前，插入深度休眠处理块：
```python
                idle_seconds = read_input_idle_seconds()

                # --- 深度休眠处理（在开摄像头之前）---
                if deep_sleep:
                    action = deep_sleep_decision(
                        True, currently_away, idle_seconds, now - last_cam_peek)
                    if action == "stay_sleep":
                        self._sleep(DEEP_SLEEP_POLL_SECONDS)
                        continue
                    if action == "wake":
                        deep_sleep = False
                        log_event(self.event_logger, "deep_sleep_exit",
                                  trigger="input",
                                  duration_s=round(now - deep_sleep_start, 1),
                                  num_peeks=peek_count)
                        # 落到下方正常检测路径（会重开摄像头）
                    elif action == "peek_camera":
                        last_cam_peek = now
                        peek_count += 1
                        peeking = True
                        # 落到下方正常检测路径，跑一次检测后据结果决定去留
```

- [ ] **Step 6: away 分支记 snapshot + 触发进入**

在 `core.py:347` 的 `self.stats.record("away", now)` 之前插入（此处 `not person_present` 已成立）：
```python
                    currently_away = True
                    if not away_idle_logged:
                        log_event(self.event_logger, "away_idle_snapshot",
                                  idle_seconds=idle_seconds)
                        away_idle_logged = True
                    # 进入深度休眠：away 且键鼠空闲达门槛
                    if (not deep_sleep
                            and deep_sleep_decision(False, True, idle_seconds, 0.0) == "enter"):
                        deep_sleep = True
                        deep_sleep_start = now
                        last_cam_peek = now
                        peek_count = 0
                        log_event(self.event_logger, "deep_sleep_enter",
                                  idle_seconds=idle_seconds)
                        if cap is not None:
                            cap.release()
                            cap = None
```

- [ ] **Step 7: 兜底瞄帧后据结果决定去留 + present 分支清 away 标志**

在 `core.py:414` 的 `else:`（`person_present` 为真的分支，`present_streak += 1` 那行之前）插入清标志：
```python
                    currently_away = False
                    away_idle_logged = False
```
然后在该 `else` 分支**末尾**（`core.py:428` 的 `away_start_time = None` 之后）加：
```python
                    if peeking:
                        peeking = False
                        # 兜底瞄到人 → 退出深度休眠
                        log_event(self.event_logger, "deep_sleep_exit",
                                  trigger="camera",
                                  duration_s=round(now - deep_sleep_start, 1),
                                  num_peeks=peek_count)
```
并在 `not person_present` 分支（`core.py:413` 的 `self._notify_state("away")` 之后）加：兜底瞄帧没瞄到人则回休眠：
```python
                    if peeking:
                        peeking = False
                        log_event(self.event_logger, "camera_peek",
                                  found_person=False, idle_seconds=idle_seconds)
                        if cap is not None:
                            cap.release()
                            cap = None
```

- [ ] **Step 8: 验证 import + 现有测试不破**

Run: `source .venv/bin/activate && python -c "import sit_monitor.core" && python -m pytest tests/test_idle.py tests/test_posture.py tests/test_progression.py -q`
Expected: PASS（import 成功，相关测试通过）

- [ ] **Step 9: 提交**

```bash
git add sit_monitor/core.py
git commit -m "feat: core 接入深度休眠三态 + deepsleep_events 埋点

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 离线评估脚本 eval_deep_sleep.py

**Files:**
- Create: `scripts/eval_deep_sleep.py`
- Test: `tests/test_eval_deep_sleep.py`

**Interfaces:**
- Produces: `summarize(events: list[dict], posture_count_by_hour: dict[str, int]) -> dict` — 纯函数，输入事件列表 + 每小时 posture 条数，返回评估指标 dict。CLI `main()` 读 `deepsleep_events.jsonl` + `posture.jsonl` 后调 `summarize` 并打印。

- [ ] **Step 1: 写失败测试**

`tests/test_eval_deep_sleep.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from eval_deep_sleep import summarize


def _events():
    return [
        {"event": "deep_sleep_enter", "idle_seconds": 300.0},
        {"event": "deep_sleep_exit", "trigger": "input", "duration_s": 1200.0, "num_peeks": 3},
        {"event": "deep_sleep_enter", "idle_seconds": 305.0},
        {"event": "camera_peek", "found_person": False, "idle_seconds": 600.0},
        {"event": "deep_sleep_exit", "trigger": "camera", "duration_s": 800.0, "num_peeks": 2},
    ]


def test_counts_sessions_and_durations():
    r = summarize(_events(), {})
    assert r["sessions"] == 2
    assert r["total_sleep_seconds"] == 2000.0          # 1200 + 800
    assert r["exit_trigger"] == {"input": 1, "camera": 1}


def test_camera_triggered_sessions_flagged():
    # camera 触发＝人回来没碰键鼠，覆盖缺口指标
    r = summarize(_events(), {})
    assert r["camera_exit_ratio"] == 0.5               # 1/2


def test_empty_events():
    r = summarize([], {})
    assert r["sessions"] == 0
    assert r["total_sleep_seconds"] == 0.0
    assert r["camera_exit_ratio"] == 0.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/test_eval_deep_sleep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_deep_sleep'`

- [ ] **Step 3: 写 eval_deep_sleep.py**

`scripts/eval_deep_sleep.py`:
```python
#!/usr/bin/env python3
"""离线评估深度休眠效果：读 deepsleep_events.jsonl + posture.jsonl，输出报告。

省电侧：累计休眠时长、会话数、估算省下的摄像头开启次数。
漏检风险侧：退出触发分布（input vs camera）、camera 触发占比（覆盖缺口）。
不依赖运行中进程，可随时跑。
"""
import json
import os
import sys


def summarize(events, posture_count_by_hour):
    """聚合事件，返回评估指标 dict。"""
    sessions = 0
    total_sleep = 0.0
    trigger = {"input": 0, "camera": 0}
    short_exits = 0  # 进入后 <30s 即退出（疑似睡早了）
    for e in events:
        if e.get("event") == "deep_sleep_exit":
            sessions += 1
            total_sleep += float(e.get("duration_s", 0.0))
            tg = e.get("trigger")
            if tg in trigger:
                trigger[tg] += 1
            if float(e.get("duration_s", 0.0)) < 30:
                short_exits += 1
    camera_exit_ratio = (trigger["camera"] / sessions) if sessions else 0.0
    return {
        "sessions": sessions,
        "total_sleep_seconds": total_sleep,
        "exit_trigger": trigger,
        "camera_exit_ratio": camera_exit_ratio,
        "short_exits": short_exits,
        "posture_count_by_hour": posture_count_by_hour,
    }


def _read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _posture_by_hour(records):
    by_hour = {}
    for r in records:
        ts = r.get("ts", "")
        hour = ts[:13]  # 'YYYY-MM-DDTHH'
        if hour:
            by_hour[hour] = by_hour.get(hour, 0) + 1
    return by_hour


def main():
    log_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    events = _read_jsonl(os.path.join(log_dir, "deepsleep_events.jsonl"))
    posture = _read_jsonl(os.path.join(log_dir, "posture.jsonl"))
    r = summarize(events, _posture_by_hour(posture))
    print(f"深度休眠会话数: {r['sessions']}")
    print(f"累计休眠时长: {r['total_sleep_seconds']/3600:.2f} 小时")
    print(f"退出触发: input={r['exit_trigger']['input']} camera={r['exit_trigger']['camera']}")
    print(f"camera 触发占比(覆盖缺口指标): {r['camera_exit_ratio']*100:.0f}%")
    print(f"疑似睡早(进入<30s 即退出)次数: {r['short_exits']}")
    hours = sorted(r["posture_count_by_hour"])
    if hours:
        vals = [r["posture_count_by_hour"][h] for h in hours]
        print(f"posture 检测密度: {len(hours)} 小时, 每小时均值 {sum(vals)/len(vals):.0f} 条")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/test_eval_deep_sleep.py -q`
Expected: PASS（3 个测试）

- [ ] **Step 5: 提交**

```bash
git add scripts/eval_deep_sleep.py tests/test_eval_deep_sleep.py
git commit -m "feat: 深度休眠离线评估脚本 eval_deep_sleep.py

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec 覆盖：**
- 系统空闲读取（Quartz，失败回 None）→ Task 1 `read_input_idle_seconds` ✅
- 三态决策（enter/stay/peek/wake/none）→ Task 1 `deep_sleep_decision` + 测试 ✅
- 进入条件 away 且空闲≥300 → Task 1 决策 + Task 2 Step 6 ✅
- 休眠期关摄像头、~2s 轮询、每 300s 瞄一眼 → Task 2 Step 5/7 ✅
- 唤醒：键鼠活动（<5s）或瞄到人 → Task 2 Step 5（wake）/Step 7（camera exit）✅
- 取不到空闲退回现有行为 → Task 1（None→none/wake failsafe）✅
- 不喂 progression（沿用 away）→ 深度休眠 `continue` 在喂 progression 之前，不进入 away 分支；唤醒/瞄帧才走正常检测 ✅
- 菜单栏沿用 away 显示 → 未改图标逻辑 ✅
- 埋点 4 事件（enter/peek/exit/away_idle_snapshot）→ Task 2 Step 5/6/7 ✅
- 离线评估脚本 → Task 3 ✅

**占位符扫描：** 无 TBD/TODO；每个代码 step 均为完整代码 ✅。

**类型一致性：** `deep_sleep_decision(in_deep_sleep, is_away, idle_seconds, secs_since_peek)` 签名在 Task 1 定义、Task 2 Step 5/6 调用一致 ✅；`read_input_idle_seconds()` 返回 `float|None`，Task 2 传给决策一致 ✅；`log_event(logger, event_type, **kwargs)` 复用现有签名 ✅；`summarize(events, posture_count_by_hour)` Task 3 定义与测试调用一致 ✅。

**已知约束：** Task 2 的循环改动无法纯单测（依赖真摄像头/真键鼠/真循环），靠 import 校验 + Self-Review 的事件次序推演 + 部署后看 deepsleep_events.jsonl 手测覆盖；纯逻辑（决策/评估）已被 Task 1/3 单测充分覆盖。
