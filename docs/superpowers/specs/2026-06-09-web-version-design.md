# 网页版坐姿监控 — 设计文档

## 背景与目标

桌面版（Python + rumps）需要安装、且分平台。做一个**网页版**，用户直接打开
浏览器就能用，零安装、跨平台、隐私（画面全程本地处理不上传），降低使用门槛。

**核心价值**：打开网页 → 授权摄像头（一次）→ 实时姿势检测 → 不良姿势时
多渠道提醒。

**根本取舍（相比桌面版）**：没有常驻菜单栏图标；浏览器标签页需开着才能监控。
提醒靠浏览器通知 / 声音 / 标签页标题+favicon。

## 范围（MVP）

**包含：**
- 实时姿势检测（MediaPipe Web，本地 WASM）
- 监控台界面：摄像头画面 + 骨骼线 + 标准参考线 + 状态条
- 4 类姿势问题 + 方向：头向左/右歪、左/右肩高、前倾、躯干前倾
- 久坐计时提醒（纯计时，默认 45 分钟）
- 提醒三管齐下：浏览器通知 + 提示音 + 标签页 title/favicon 变化
- 设置（阈值 / 语言 zh-en / 各提醒开关），存 localStorage

**暂不含（YAGNI，留后续）：**
- 疲劳检测（需额外 FaceLandmarker + 眨眼/哈欠 EAR/MAR 移植，较重）
- 历史统计图表
- 云账号 / 跨设备同步

## 技术栈

- 原生 HTML/CSS/JS（无框架，保持轻量、直接挂 GitHub Pages）
- `@mediapipe/tasks-vision`（CDN）— PoseLandmarker，WASM/WebGL 浏览器本地推理
- 无后端、无构建步骤

## 架构与模块

各模块单一职责、可独立测试：

| 模块 | 职责 | 依赖 |
|------|------|------|
| `camera.js` | `getUserMedia` 拿摄像头流 → `<video>` | 浏览器 API |
| `detector.js` | 加载 PoseLandmarker，每帧出 landmarks | tasks-vision |
| `posture.js` | 角度判定（肩倾/头倾/前倾/躯干）→ `{is_bad, problems, dirs}` | 无 |
| `overlay.js` | canvas 画骨骼线 + 参考线 | 无 |
| `reminder.js` | 防抖后触发通知 / 声音 / 标签页 title+favicon | 浏览器 API |
| `settings.js` | 阈值/语言/开关 ↔ localStorage | 无 |
| `i18n.js` | zh/en 文案（移植桌面版） | 无 |
| `app.js` | 主循环串联 + 状态条 UI | 以上全部 |

### 数据流

```
camera(<video>) ──► detector(landmarks, ~1s 节流) ──► posture(评估)
                                                       ├──► overlay  (骨骼+参考线 → <canvas>)
                                                       ├──► 状态条   (✓/箭头/倾斜线/时钟 符号语义)
                                                       └──► reminder (防抖 → 通知/声音/标签页)
```

### 页面布局（监控台）

- 居中 `<video>` + 叠加 `<canvas>`（骨骼线 / 参考线）
- 下方状态条：复用桌面版 v1.5.2 图标符号语义
  （绿✓=好 / 橙箭头=该往那调 / 橙倾斜线=肩歪 / 红时钟=久坐）
- 角落设置按钮（阈值 / 语言 / 提醒开关）
- 首屏：授权引导 + 「开始监控」按钮

## 复用桌面版资产

- **posture 角度算法 + 阈值默认值**（`sit_monitor/posture.py` 移植为 JS）
- **overlay 骨骼连线 + 参考线画法**（`sit_monitor/overlay.py` 思路）
- **i18n zh/en 文案**（`sit_monitor/i18n/`）
- **图标符号语义**（v1.5.2 状态条：方向箭头 / 倾斜线 / 时钟）

方向语义沿用桌面版：箭头指「该往哪调」（纠正方向）；优先级 久坐 > 姿势偏 > 好。

## 错误处理 / 边界

| 情况 | 处理 |
|------|------|
| 摄像头被拒绝/无设备 | 友好引导页：说明需要摄像头 + 如何开启权限 |
| 通知权限被拒 | 降级到「标签页 title/favicon + 声音」，不强制 |
| HTTPS 要求 | `getUserMedia` 需安全上下文；GitHub Pages 是 https，本地用 localhost |
| 检测不到人 | 状态条灰色待机（away 语义） |
| 切到后台标签 | `visibilitychange` → 降频检测，通知照常推送 |
| 浏览器不支持 | 检测 WebGL/WASM，否则提示用 Chrome/Edge/Safari 新版 |

## 性能

- 检测节流约 1 秒/次（与桌面版一致、省电、避免 WASM 持续占 CPU）
- overlay 平滑显示最近骨骼；后台标签降频
- MediaPipe 模型首次从 CDN 加载约几 MB，浏览器缓存后秒开

## 部署

- 应用放 `docs/web/`，与落地页 `docs/index.html` 同源
- 落地页加「▶ 在线试用」按钮链过去
- GitHub Pages 自动部署（项目已启用 Pages）

## 测试

- **单元**：`posture.js` 是纯函数 — 喂 landmarks → 验证 problems/方向，
  可移植桌面版测试用例
- **手测**：真实浏览器摄像头逐姿势验证；Chrome/Safari 兼容；
  通知/声音/标签页三种提醒；摄像头拒绝/通知拒绝的降级路径

## 待澄清 / 后续

- 疲劳检测、历史统计、云同步为后续迭代，各自独立成 spec
- 左右方向若与实际相反（摄像头镜像），翻转方向判断即可（与桌面版同处理）
