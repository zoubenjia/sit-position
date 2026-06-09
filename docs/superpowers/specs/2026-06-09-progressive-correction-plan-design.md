# 渐进式纠正计划 — 设计文档（桌面版）

## 背景与目标

固定的严格阈值让用户一上来就受挫——满屏"前倾/坏姿势"，没有正反馈（实测中
`neck` 常态 22° 持续超 20° 阈值、图标卡死前倾就是这个问题）。

**渐进式纠正计划**反过来：从宽松阈值起步，让用户大部分时间看到"✓ 良好"、有成就
感；随实际表现达标，逐渐收紧阈值，在不知不觉中养成标准坐姿。本质是把"监控工具"
变成"陪用户循序渐进的纠正计划/教练"。

先在**桌面版**实现（用户日常常驻使用 + 已有每日统计数据基础），渐进逻辑设计成
纯模块、可后续复用到网页版。

## 核心机制

### 阶段表（5 阶段，所有阈值联动，阶段 5 = 现有标准默认值）

| 阶段 | neck | head_tilt | shoulder | torso |
|------|------|-----------|----------|-------|
| 1 宽松 | 30° | 18° | 16° | 12° |
| 2 | 27° | 16° | 14° | 11° |
| 3 | 24° | 14° | 12° | 10° |
| 4 | 22° | 13° | 11° | 9° |
| 5 标准 | 20° | 12° | 10° | 8° |

### 进阶（表现驱动）

- 每日「良好率」= 当日 good 时长 ÷ (good + bad 时长)；away 不计入分母
- **连续 3 天良好率 ≥ 80%** → 解锁下一阶段、阈值收紧
- **只升不降**：表现退步不自动降级（建立信心、不惩罚低谷）
- 阶段 5 为"毕业"，不再进阶
- 进阶时弹**鼓励通知**：`🎉 恭喜进入阶段 N！坐姿标准又近了一步`

### 起点与手动调整

- 所有人从**阶段 1**（最宽松）起步
- 菜单提供「手动调整阶段」，允许想自定进度的用户直接跳阶段

## 数据与持久化

新模块 `sit_monitor/progression.py` — `ProgressionTracker`：

**状态文件** `progression.json`（`log_dir`，与 achievements.json 同目录）：
```json
{
  "stage": 3,
  "stage_since": "2026-06-07",
  "current_day": "2026-06-09",
  "today_good_seconds": 1820.5,
  "today_bad_seconds": 240.0,
  "recent_days": [
    {"date": "2026-06-07", "good_ratio": 0.86},
    {"date": "2026-06-08", "good_ratio": 0.91}
  ],
  "consecutive_met": 2
}
```

**职责：**
- `record(state, now)` — 累计当日 good/bad 秒（输入与 `Stats.record` 同源）
- 跨自然日检测：`now` 跨过 `current_day` 时，结算昨日 `good_ratio`、追加到
  `recent_days`、判定是否进阶（连续达标计数）、重置当日累计、落盘
- `current_thresholds()` — 按当前 `stage` 查阶段表返回 `{shoulder, neck, torso, head_tilt}`
- `progress_summary()` — 返回 `{stage, today_ratio, consecutive_met, target_days}` 供 UI
- 只升不降：`consecutive_met >= 3` 且 `stage < 5` 时 `stage++`、清零计数、记 `stage_since`

## 与现有监控集成

- `core.PostureMonitor`：每次 `self.stats.record(state, now)` 后，同步
  `self.progression.record(state, now)`
- 取阈值改造：`evaluate_posture(lm, thresholds)` 的 `thresholds` 来源，从固定
  `s.thresholds` 改为：渐进开启时用 `self.progression.current_thresholds()`，
  关闭时用 `s.thresholds`（固定）
- `core` 在主循环检测跨天 / 进阶，进阶时通过 `on_state_change` 或直接
  `rumps.notification` 发鼓励通知（tray 层处理通知，core 通过回调上报进阶事件）

## 设置与开关

- `Settings` 增加 `progressive_enabled: bool = True`（**默认开**）
  - 渐进从宽松起步，对现有用户是"放松初期标准"，体验更友好
  - 关闭则回退固定阈值（用阶段 5 标准值或用户自定义 `*_threshold`）
- tray 设置菜单加「☑ 渐进式计划」开关
- tray 菜单显示进度项：`纠正计划：阶段 3/5 · 今日良好率 85% · 连续达标 2/3 天`
- 菜单栏图标语义不变（仍按当前姿势绿✓/橙箭头/红时钟）；渐进只影响判定阈值

## 单元划分

- `progression.py`（新，纯逻辑）— 阶段表、进阶判定、跨天结算、查表。可独立单测
- `core.py`（改）— 集成 record + 阈值来源 + 进阶事件上报
- `tray.py`（改）— 进度菜单项、开关、进阶通知
- `settings.py`（改）— `progressive_enabled` 字段
- `i18n/{zh,en}.py`（改）— 阶段/进阶/进度文案

边界清晰：进阶逻辑全在 progression.py（可测），core 只喂数据 + 取阈值，tray 只展示。

## 错误处理 / 边界

| 情况 | 处理 |
|------|------|
| progression.json 不存在/损坏 | 回退初始状态（阶段 1），重新落盘 |
| 当日无数据（good+bad=0） | 该日不计入连续达标（不算达标也不算失败，跳过） |
| 进程跨多天未运行 | 缺失日不计入连续序列（连续计数按有数据的自然日） |
| 用户手动调阶段 | 直接设 stage、清零连续计数、记 stage_since |
| 关闭渐进模式 | 用固定阈值；progression 状态保留（重开延续进度） |

## 测试

- **单元**（`progression.py`）：阶段查表、连续 3 天达标进阶、只升不降、阶段 5 毕业
  不再进阶、跨天结算、无数据日跳过、损坏文件回退
- **集成手测**：菜单显示进度、进阶鼓励通知、开关切换回固定阈值、手动调阶段

## 范围与后续

- **本期**：桌面版渐进计划（机制 + 数据 + 菜单 UI + 开关）
- **后续**：移植到网页版（复用阶段表 + 进阶判定逻辑，网页用 localStorage 做每日统计）；
  首次个性化校准起点（YAGNI，暂不做，所有人从阶段 1）
