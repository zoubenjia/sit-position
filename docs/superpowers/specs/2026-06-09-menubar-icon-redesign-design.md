# 菜单栏图标重设计 — 可操作的状态指示

## 背景与问题

原菜单栏图标是 22px 侧视小人 + 颜色（绿/橙/红/灰），问题类型靠小人身上
几乎不可见的高亮标记（箭头、波浪线）区分。实际使用中用户无法分辨：
- 该往左还是往右调整姿势
- 是"姿势偏了该调整"还是"久坐/疲劳该休息"

诊断信息其实是齐全的（头向左/右歪、左/右肩高、前倾角、久坐分钟、疲劳程度），
但只在点开菜单时才能看到；菜单栏本身只传达了颜色。

## 设计决策

**用单个占满整个图标的大符号，砍掉小人细节，换取 22px 下的辨识度。**

不同状态长得**截然不同**（而非同一小人的细微差异），这样真实尺寸也能一眼区分。

### 状态 → 符号映射

| 状态 | 符号 | 颜色 | 含义 |
|------|------|------|------|
| 姿势好 | 对勾 ✓ | 绿 | 无需动作 |
| 头/身偏左 | 箭头 → | 橙 | 该向右摆正 |
| 头/身偏右 | 箭头 ← | 橙 | 该向左摆正 |
| 前倾/驼背 | 箭头 ↑ | 橙 | 该坐直 |
| 左肩高 | 倾斜线 `\` + 水平基准 | 橙 | 该放平（左高） |
| 右肩高 | 倾斜线 `/` + 水平基准 | 橙 | 该放平（右高） |
| 久坐 ≥45min | 时钟 | 红 | 该起身 |
| 疲劳 | 月亮 | 红 | 该休息 |
| 运动中 | 俯卧撑小人 | 蓝 | 锻炼模式 |
| 待机/离开 | 空心圆环 | 灰 | 未监控/无人 |

### 关键语义

- **箭头方向 = "该往哪调"**（纠正方向），不是"现在歪向哪"。用户看箭头直接照做。
- **优先级：运动 > 待机 > 疲劳 > 久坐 > 姿势偏 > 好**。多个状态同时发生时显示
  更紧急的——"起身/休息"比"调姿势"优先，因为起身后姿势问题也跟着重置。

## 架构与数据流

```
posture.evaluate_posture()
  └─ details 新增 shoulder_dir(+1左高/-1右高), head_tilt_dir(+1右歪/-1左歪)
       │  （角度本身被 abs，故方向符号单独存）
       ▼
core.PostureMonitor._notify_state(state, details=, problems=, sit_minutes=, fatigue=)
       ▼
tray.TrayApp._on_state_change → self._details
       ▼
tray._poll_ui_update（主线程定时器，0.5s）→ _set_icon(state, details)
       │
       ├─ _icon_symbol(state, details)  ← 优先级决策，返回 symbol 字符串
       ▼
icon_gen.symbol_path(symbol) → 生成 22px/44px PNG（缓存）
```

### 单元职责

- **posture.py** — 只负责算姿势 + 方向符号，不关心图标
- **tray._icon_symbol** — 纯决策：state + details → symbol 字符串（可独立测试）
- **icon_gen.generate_symbol / symbol_path** — 纯绘制：symbol → PNG（无业务逻辑）

边界清晰：决策与绘制分离，新增一种状态只需在两处各加一行。

## 顺带修复（同版本）

1. **certifi 缺失致监控崩溃** — mediapipe≥0.10.35 运行时调 `certifi.where()` 但未声明
   依赖；pyproject 补 `certifi`，formula 安装时 `--ignore-installed certifi` 绕过
   全局空 certifi 目录的遮蔽。
2. **睡眠唤醒后图标卡住** — UI 定时器改回 `@rumps.timer` 装饰器注册（显式
   `rumps.Timer` 在 NSApplication 启动流程下不触发），并监听
   `NSWorkspaceDidWakeNotification` 唤醒后重建定时器。

## 测试

- `_icon_symbol` 决策逻辑：11 个用例覆盖各状态 + 优先级 + 方向映射（全通过）
- `generate_symbol`：9 种符号生成验证（颜色/非空）
- 真实菜单栏：装到运行版逐状态实测

## 待校准

肩膀/头部左右方向若与实际相反（摄像头镜像），翻转 `shoulder_dir`/`head_tilt_dir`
判断即可——绘制不变。
