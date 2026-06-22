# 输入空闲 + 摄像头确认的深度休眠 Implementation Plan（桌面版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 人真不在（摄像头判定 away 且键鼠空闲≥5 分钟）时进入深度休眠——关摄像头、每 2s 轻量轮询、碰键鼠即唤醒——并埋点以便事后评估省电效果。

**Architecture:** 新增纯逻辑模块 `idle.py`（读系统空闲秒数 + 三态决策函数，可单测，不依赖真摄像头/真键鼠）。`core.py` 主循环顶部接入决策、按结果进入/维持/唤醒，并把状态转移事件写入独立的 `deepsleep_events.jsonl`（复用现有 `log_event`）。离线脚本 `scripts/eval_deep_sleep.py` 读日志聚合评估报告。

**Tech Stack:** Python，pytest（`tests/test_*.py`），Quartz（`CGEventSourceSecondsSinceLastEventType`，macOS 专有，失败回退），RotatingFileHandler JSON 日志。

## Global Constraints

- 系统空闲读取失败（非 mac / Quartz 异常）→ `read_input_idle_seconds()` 返回 `None`，整套深度休眠**退回现有行为**，不影响其它平台。
- 退出**纯靠键鼠唤醒，无摄像头兜底**（主动用电脑必触发键鼠；被动看屏不监测姿势可接受）。
- 参数为模块常量（本期不提为 Settings）：`ENTER_IDLE_SECONDS=300.0`、`WAKE_IDLE_SECONDS=5.0`、`DEEP_SLEEP_POLL_SECONDS=2.0`。
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
  - `deep_sleep_decision(in_deep_sleep: bool, is_away: bool, idle_seconds: float | None) -> str` — 返回 `"enter"` / `"wake"` / `"stay_sleep"` / `"none"`。
  - 模块常量 `ENTER_IDLE_SECONDS`、`WAKE_IDLE_SECONDS`、`DEEP_SLEEP_POLL_SECONDS`。

- [ ] **Step 1: 写失败测试**

`tests/test_idle.py`:
```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/test_idle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sit_monitor.idle'`

- [ ] **Step 3: 写 idle.py**

`sit_monitor/idle.py`:
```python
"""系统输入空闲读取 + 深度休眠三态决策（纯逻辑，可单测）。

人真不在（摄像头 away 且键鼠长时间空闲）时进入深度休眠：关摄像头、
仅极低频轮询空闲秒数；碰键鼠即唤醒（不做摄像头兜底）。
"""

# 参数（本期为模块常量，未提为 Settings）。
ENTER_IDLE_SECONDS = 300.0       # 进入深度休眠的键鼠空闲门槛（且须同时 away）
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


def deep_sleep_decision(in_deep_sleep, is_away, idle_seconds):
    """根据当前状态与信号决定动作。

    in_deep_sleep: 当前是否已处于深度休眠
    is_away:       最近一次摄像头检测是否判定无人（仅用于"进入"判定）
    idle_seconds:  键鼠空闲秒数；None＝取不到（feature 不可用）

    返回 "enter" / "wake" / "stay_sleep" / "none"。
    """
    if not in_deep_sleep:
        if idle_seconds is None:
            return "none"  # 取不到空闲 → 永不进入，退回现有行为
        if is_away and idle_seconds >= ENTER_IDLE_SECONDS:
            return "enter"
        return "none"

    # 已在深度休眠：仅靠键鼠唤醒
    if idle_seconds is None:
        return "wake"  # failsafe：信号不可用就唤醒回正常检测
    if idle_seconds < WAKE_IDLE_SECONDS:
        return "wake"  # 刚有键鼠输入
    return "stay_sleep"
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `source .venv/bin/activate && python -m pytest tests/test_idle.py -q`
Expected: PASS（8 个测试）

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
- Consumes: `idle.read_input_idle_seconds`, `idle.deep_sleep_decision`, 常量 `DEEP_SLEEP_POLL_SECONDS`；现有 `log_event(logger, event_type, **kwargs)`、`self._sleep`。
- Produces: 写 `deepsleep_events.jsonl`，事件 `deep_sleep_enter` / `deep_sleep_exit` / `away_idle_snapshot`（字段见 spec）。

**Context:** 主循环在 `core.py:231` 的 `while self.running:`。`now = time.time()` 在 `core.py:232`。away 分支（`if not person_present:`）在 `core.py:323`，其中 `self.stats.record("away", now)` 在 `core.py:347`。present 分支 `else:` 在 `core.py:414`。`setup_logging()` 在 `core.py:32`。

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
        # --- 深度休眠：away 且键鼠长时间空闲时关摄像头、仅轮询键鼠直到唤醒 ---
        deep_sleep = False
        deep_sleep_start = 0.0     # 本次休眠进入时刻
        currently_away = False     # 最近一次检测是否判定无人（供进入判定）
        away_idle_logged = False   # 本次 away 是否已记 away_idle_snapshot
```

- [ ] **Step 5: 循环顶部接入休眠处理**

在 `core.py:232` 的 `now = time.time()` 之后、`# 运行中实时读取设置` 之前，插入深度休眠处理块：
```python
                idle_seconds = read_input_idle_seconds()

                # --- 深度休眠处理（在开摄像头之前）---
                if deep_sleep:
                    action = deep_sleep_decision(True, currently_away, idle_seconds)
                    if action == "stay_sleep":
                        self._sleep(DEEP_SLEEP_POLL_SECONDS)
                        continue
                    # action == "wake"：退出休眠，落到下方正常检测路径（会重开摄像头）
                    deep_sleep = False
                    log_event(self.event_logger, "deep_sleep_exit",
                              duration_s=round(now - deep_sleep_start, 1))
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
                            and deep_sleep_decision(False, True, idle_seconds) == "enter"):
                        deep_sleep = True
                        deep_sleep_start = now
                        log_event(self.event_logger, "deep_sleep_enter",
                                  idle_seconds=idle_seconds)
                        if cap is not None:
                            cap.release()
                            cap = None
```

- [ ] **Step 7: present 分支清 away 标志**

在 `core.py:414` 的 `else:`（`person_present` 为真的分支）里、`present_streak += 1` 那行之前插入：
```python
                    currently_away = False
                    away_idle_logged = False
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
- Produces: `summarize(events: list[dict], posture_count_by_hour: dict[str, int]) -> dict` — 纯函数，输入事件列表 + 每小时 posture 条数，返回评估指标 dict（keys: `sessions`, `total_sleep_seconds`, `short_exits`, `posture_count_by_hour`）。CLI `main()` 读 `deepsleep_events.jsonl` + `posture.jsonl` 后调 `summarize` 并打印。

- [ ] **Step 1: 写失败测试**

`tests/test_eval_deep_sleep.py`:
```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/test_eval_deep_sleep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_deep_sleep'`

- [ ] **Step 3: 写 eval_deep_sleep.py**

`scripts/eval_deep_sleep.py`:
```python
#!/usr/bin/env python3
"""离线评估深度休眠效果：读 deepsleep_events.jsonl + posture.jsonl，输出报告。

省电侧：累计休眠时长、会话数、posture 检测密度（每小时条数）。
误进入侧：进入后 <30s 即退出的会话数（疑似睡早）。
不依赖运行中进程，可随时跑。
"""
import json
import os
import sys


def summarize(events, posture_count_by_hour):
    """聚合事件，返回评估指标 dict。"""
    sessions = 0
    total_sleep = 0.0
    short_exits = 0  # 进入后 <30s 即退出（疑似睡早了）
    for e in events:
        if e.get("event") == "deep_sleep_exit":
            sessions += 1
            dur = float(e.get("duration_s", 0.0))
            total_sleep += dur
            if dur < 30:
                short_exits += 1
    return {
        "sessions": sessions,
        "total_sleep_seconds": total_sleep,
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
- 三态决策（enter/wake/stay_sleep/none）→ Task 1 `deep_sleep_decision` + 测试 ✅
- 进入条件 away 且空闲≥300 → Task 1 决策 + Task 2 Step 6 ✅
- 休眠期关摄像头、~2s 轮询、不开摄像头 → Task 2 Step 5/6 ✅
- 唤醒：仅键鼠活动（<5s）或 None failsafe → Task 1 + Task 2 Step 5 ✅
- 取不到空闲退回现有行为 → Task 1（None→none / 休眠中 None→wake）✅
- 不喂 progression → 深度休眠 `stay_sleep` 时 `continue` 在喂 progression 之前 ✅
- 菜单栏沿用 away 显示 → 未改图标逻辑 ✅
- 埋点 3 事件（enter/exit/away_idle_snapshot）→ Task 2 Step 5/6 ✅
- 离线评估脚本 → Task 3 ✅

**占位符扫描：** 无 TBD/TODO；每个代码 step 均为完整代码 ✅。

**类型一致性：** `deep_sleep_decision(in_deep_sleep, is_away, idle_seconds)` 签名 Task 1 定义、Task 2 Step 5/6 调用一致（3 参，无 secs_since_peek）✅；`read_input_idle_seconds()` 返回 `float|None` 一致 ✅；`log_event(logger, event_type, **kwargs)` 复用现有 ✅；`summarize(events, posture_count_by_hour)` 返回 keys（sessions/total_sleep_seconds/short_exits/posture_count_by_hour）与测试一致 ✅。

**已知约束：** Task 2 的循环改动无法纯单测（依赖真摄像头/真键鼠/真循环），靠 import 校验 + 部署后看 deepsleep_events.jsonl 手测覆盖；纯逻辑（决策/评估）已被 Task 1/3 单测充分覆盖。
