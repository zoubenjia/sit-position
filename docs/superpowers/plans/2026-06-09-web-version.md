# 网页版坐姿监控 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯前端网页版坐姿监控 MVP — 打开浏览器授权摄像头，本地 MediaPipe 实时姿势检测，不良姿势时通知/声音/标签页三管齐下提醒。

**Architecture:** 无框架原生 HTML/CSS/JS（ES modules），`@mediapipe/tasks-vision` CDN 加载在浏览器本地推理。模块单一职责：camera→detector→posture→{overlay, 状态条, reminder}。无后端、无构建步骤，挂 GitHub Pages（`docs/web/`）。

**Tech Stack:** ES modules、`@mediapipe/tasks-vision`（PoseLandmarker WASM）、Canvas 2D、Web Notification API、Web Audio、localStorage。测试用 Node 内置 `node --test`（仅纯逻辑模块）。

---

## 文件结构

```
docs/web/
  index.html            — 监控台页面（video + canvas + 状态条 + 设置）
  css/style.css         — 样式（深色，呼应落地页）
  js/
    landmarks.js        — MediaPipe Pose 关键点索引常量（纯数据）
    posture.js          — 角度计算 + 坐姿判定（纯函数，可 node 测）
    i18n.js             — zh/en 文案 + 当前语言
    settings.js         — 阈值/语言/提醒开关 ↔ localStorage（纯逻辑，可测）
    iconSymbol.js       — 状态→符号决策（纯函数，复用 v1.5.2 语义，可测）
    camera.js           — getUserMedia → <video>
    detector.js         — 加载 PoseLandmarker，detectForVideo
    overlay.js          — canvas 画骨骼线 + 参考线
    reminder.js         — 防抖 → 通知 / 声音 / 标签页 title+favicon
    app.js              — 主循环串联 + 状态条 UI + 授权引导
  test/
    posture.test.mjs    — posture 纯函数单元测试
    settings.test.mjs   — settings 单元测试
    iconSymbol.test.mjs — 符号决策单元测试
```

测试运行环境：项目根目录 `node --test docs/web/test/`（Node ≥18，内置 test runner，无需 npm install）。

---

## Task 1: 关键点索引常量 + posture 角度函数（TDD）

**Files:**
- Create: `docs/web/js/landmarks.js`
- Create: `docs/web/js/posture.js`
- Test: `docs/web/test/posture.test.mjs`

- [ ] **Step 1: 写关键点常量**

`docs/web/js/landmarks.js`:
```js
// MediaPipe Pose 33 点索引（与 Python mediapipe PoseLandmark 枚举一致）
export const LM = {
  NOSE: 0,
  LEFT_EAR: 7, RIGHT_EAR: 8,
  LEFT_SHOULDER: 11, RIGHT_SHOULDER: 12,
  LEFT_HIP: 23, RIGHT_HIP: 24,
  LEFT_KNEE: 25, RIGHT_KNEE: 26,
};
```

- [ ] **Step 2: 写失败测试**

`docs/web/test/posture.test.mjs`:
```js
import { test } from "node:test";
import assert from "node:assert";
import { shoulderTilt, headTilt, headForwardAngle, torsoForwardAngle, evaluatePosture }
  from "../js/posture.js";

// 构造 33 点 landmark 数组，默认全可见、坐标居中
function lms(overrides = {}) {
  const arr = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, z: 0, visibility: 0.9 }));
  for (const [idx, v] of Object.entries(overrides)) arr[idx] = { ...arr[idx], ...v };
  return arr;
}

test("shoulderTilt: 水平肩膀返回接近 0", () => {
  const lm = lms({ 11: { x: 0.4, y: 0.5 }, 12: { x: 0.6, y: 0.5 } });
  assert.ok(Math.abs(shoulderTilt(lm)) < 0.5);
});

test("shoulderTilt: 左肩高返回正值", () => {
  // 左肩 y 更小（物理更高）→ dy = rs.y - ls.y > 0 → 正值
  const lm = lms({ 11: { x: 0.4, y: 0.4 }, 12: { x: 0.6, y: 0.5 } });
  assert.ok(shoulderTilt(lm) > 0);
});

test("shoulderTilt: 可见度低返回 null", () => {
  const lm = lms({ 11: { visibility: 0.2 } });
  assert.strictEqual(shoulderTilt(lm), null);
});

test("headTilt: 左耳高返回正值（头向右歪）", () => {
  const lm = lms({ 7: { x: 0.45, y: 0.3 }, 8: { x: 0.55, y: 0.4 } });
  assert.ok(headTilt(lm) > 0);
});

test("headForwardAngle: 耳在肩正上方返回接近 0", () => {
  const lm = lms({ 7: { x: 0.4, y: 0.3 }, 11: { x: 0.4, y: 0.5 },
                   8: { x: 0.6, y: 0.3 }, 12: { x: 0.6, y: 0.5 } });
  assert.ok(headForwardAngle(lm) < 1);
});

test("evaluatePosture: 标准坐姿无问题", () => {
  const lm = lms({ 7: { x: 0.4, y: 0.3 }, 8: { x: 0.6, y: 0.3 },
                   11: { x: 0.4, y: 0.5 }, 12: { x: 0.6, y: 0.5 },
                   23: { x: 0.4, y: 0.8 }, 24: { x: 0.6, y: 0.8 } });
  const thr = { shoulder: 10, neck: 20, torso: 8, head_tilt: 12 };
  const r = evaluatePosture(lm, thr);
  assert.strictEqual(r.isBad, false);
  assert.deepStrictEqual(r.problems, []);
});

test("evaluatePosture: 头明显侧歪 → head_tilt 问题 + 方向", () => {
  const lm = lms({ 7: { x: 0.4, y: 0.25 }, 8: { x: 0.6, y: 0.45 },  // 左耳高
                   11: { x: 0.4, y: 0.5 }, 12: { x: 0.6, y: 0.5 },
                   23: { x: 0.4, y: 0.8 }, 24: { x: 0.6, y: 0.8 } });
  const thr = { shoulder: 10, neck: 20, torso: 8, head_tilt: 12 };
  const r = evaluatePosture(lm, thr);
  assert.ok(r.problems.includes("head_tilt"));
  assert.strictEqual(r.headTiltDir, 1); // 左耳高 → +1
});
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `node --test docs/web/test/posture.test.mjs`
Expected: FAIL — `Cannot find module '../js/posture.js'`

- [ ] **Step 4: 写 posture.js 实现**

`docs/web/js/posture.js`:
```js
import { LM } from "./landmarks.js";

// 向量 (dx, dy) 与垂直向上方向的夹角（度）
function angleDeg(dx, dy) {
  return Math.abs(Math.atan2(dx, -dy) * 180 / Math.PI);
}

// 肩膀倾斜角：正值=左肩高右肩低，负值=右肩高。可见度不足返回 null
export function shoulderTilt(lm) {
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  if (ls.visibility < 0.5 || rs.visibility < 0.5) return null;
  const dy = rs.y - ls.y;            // 正值=左肩高（图像 y 向下）
  const dx = Math.abs(rs.x - ls.x);
  if (dx < 0.001) return 0;
  return Math.atan2(dy, dx) * 180 / Math.PI;
}

// 头部左右侧倾：正值=左耳高（头向右歪），负值=右耳高（头向左歪）
export function headTilt(lm) {
  const le = lm[LM.LEFT_EAR], re = lm[LM.RIGHT_EAR];
  if (le.visibility < 0.5 || re.visibility < 0.5) return null;
  const dy = re.y - le.y;            // 正值=左耳高
  const dx = Math.abs(re.x - le.x);
  if (dx < 0.001) return 0;
  return Math.atan2(dy, dx) * 180 / Math.PI;
}

// 头部前倾角：耳-肩连线与垂直线夹角，取左右平均
export function headForwardAngle(lm) {
  const le = lm[LM.LEFT_EAR], re = lm[LM.RIGHT_EAR];
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  const a = [];
  if (le.visibility >= 0.5 && ls.visibility >= 0.5) a.push(angleDeg(le.x - ls.x, le.y - ls.y));
  if (re.visibility >= 0.5 && rs.visibility >= 0.5) a.push(angleDeg(re.x - rs.x, re.y - rs.y));
  return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
}

// 躯干前倾角：肩-髋连线与垂直线夹角，取左右平均
export function torsoForwardAngle(lm) {
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  const lh = lm[LM.LEFT_HIP], rh = lm[LM.RIGHT_HIP];
  const a = [];
  if (ls.visibility >= 0.5 && lh.visibility >= 0.5) a.push(angleDeg(ls.x - lh.x, ls.y - lh.y));
  if (rs.visibility >= 0.5 && rh.visibility >= 0.5) a.push(angleDeg(rs.x - rh.x, rs.y - rh.y));
  return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
}

// 综合判定。thresholds: {shoulder, neck, torso, head_tilt}
// 返回 { isBad, problems:[], details:{}, shoulderDir, headTiltDir }
export function evaluatePosture(lm, thr) {
  const st = shoulderTilt(lm);
  const ht = headTilt(lm);
  const hf = headForwardAngle(lm);
  const tf = torsoForwardAngle(lm);
  const problems = [];
  const details = { shoulder: st, head_tilt: ht, neck: hf, torso: tf };

  if (st !== null && Math.abs(st) > thr.shoulder) problems.push("shoulder");
  if (ht !== null && Math.abs(ht) > thr.head_tilt) problems.push("head_tilt");
  if (hf !== null && hf > thr.neck) problems.push("neck");
  if (tf !== null && tf > thr.torso) problems.push("torso");

  return {
    isBad: problems.length > 0,
    problems,
    details,
    shoulderDir: st === null ? 0 : (st > 0 ? 1 : -1),   // +1左肩高 -1右肩高
    headTiltDir: ht === null ? 0 : (ht > 0 ? 1 : -1),   // +1头向右歪 -1头向左歪
  };
}
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `node --test docs/web/test/posture.test.mjs`
Expected: PASS（7 个测试全过）

- [ ] **Step 6: 提交**

```bash
git add docs/web/js/landmarks.js docs/web/js/posture.js docs/web/test/posture.test.mjs
git commit -m "feat(web): posture 角度计算与坐姿判定（移植桌面版+方向）"
```

---

## Task 2: i18n 文案

**Files:**
- Create: `docs/web/js/i18n.js`

- [ ] **Step 1: 写 i18n.js**

`docs/web/js/i18n.js`:
```js
const STRINGS = {
  zh: {
    "app.title": "坐姿监控",
    "btn.start": "开始监控",
    "btn.stop": "停止",
    "status.good": "姿势良好",
    "status.away": "未检测到人",
    "status.sit_long": "久坐了，起身活动一下",
    "problem.head_left": "头向左歪，向右摆正",
    "problem.head_right": "头向右歪，向左摆正",
    "problem.forward": "身体前倾，坐直",
    "problem.shoulder_left": "左肩偏高，放平肩膀",
    "problem.shoulder_right": "右肩偏高，放平肩膀",
    "notify.title": "坐姿提醒",
    "perm.camera": "需要摄像头权限来检测坐姿。请在浏览器允许摄像头访问。",
    "perm.unsupported": "当前浏览器不支持，请用最新版 Chrome / Edge / Safari。",
    "tab.alert": "⚠ 坐直！",
  },
  en: {
    "app.title": "Sit Monitor",
    "btn.start": "Start",
    "btn.stop": "Stop",
    "status.good": "Good posture",
    "status.away": "No person detected",
    "status.sit_long": "Sitting too long, take a break",
    "problem.head_left": "Head tilts left, straighten right",
    "problem.head_right": "Head tilts right, straighten left",
    "problem.forward": "Leaning forward, sit up",
    "problem.shoulder_left": "Left shoulder high, level them",
    "problem.shoulder_right": "Right shoulder high, level them",
    "notify.title": "Posture reminder",
    "perm.camera": "Camera access is required. Please allow camera in your browser.",
    "perm.unsupported": "Browser unsupported. Use latest Chrome / Edge / Safari.",
    "tab.alert": "⚠ Sit up!",
  },
};

let lang = "zh";
export function setLang(l) { if (STRINGS[l]) lang = l; }
export function getLang() { return lang; }
export function t(key) { return (STRINGS[lang] && STRINGS[lang][key]) || key; }
```

- [ ] **Step 2: 提交**

```bash
git add docs/web/js/i18n.js
git commit -m "feat(web): i18n zh/en 文案"
```

---

## Task 3: settings（localStorage）（TDD）

**Files:**
- Create: `docs/web/js/settings.js`
- Test: `docs/web/test/settings.test.mjs`

- [ ] **Step 1: 写失败测试**

`docs/web/test/settings.test.mjs`:
```js
import { test, beforeEach } from "node:test";
import assert from "node:assert";

// 注入内存版 localStorage（node 无 DOM）
const store = {};
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

const { loadSettings, saveSettings, DEFAULTS } = await import("../js/settings.js");

beforeEach(() => { for (const k of Object.keys(store)) delete store[k]; });

test("loadSettings: 无存储时返回默认值", () => {
  const s = loadSettings();
  assert.strictEqual(s.shoulder, DEFAULTS.shoulder);
  assert.strictEqual(s.lang, DEFAULTS.lang);
});

test("saveSettings + loadSettings: 往返一致", () => {
  saveSettings({ ...DEFAULTS, shoulder: 15, lang: "en" });
  const s = loadSettings();
  assert.strictEqual(s.shoulder, 15);
  assert.strictEqual(s.lang, "en");
});

test("loadSettings: 损坏 JSON 回退默认值", () => {
  localStorage.setItem("sitmonitor_web", "{not json");
  const s = loadSettings();
  assert.strictEqual(s.shoulder, DEFAULTS.shoulder);
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `node --test docs/web/test/settings.test.mjs`
Expected: FAIL — 找不到模块

- [ ] **Step 3: 写 settings.js**

`docs/web/js/settings.js`:
```js
const KEY = "sitmonitor_web";

export const DEFAULTS = {
  shoulder: 10, neck: 20, torso: 8, head_tilt: 12,  // 角度阈值（同桌面版）
  sit_max_minutes: 45,
  notify: true, sound: true, tab_alert: true,
  lang: "zh",
};

export function loadSettings() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveSettings(s) {
  localStorage.setItem(KEY, JSON.stringify(s));
}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `node --test docs/web/test/settings.test.mjs`
Expected: PASS（3 个测试）

- [ ] **Step 5: 提交**

```bash
git add docs/web/js/settings.js docs/web/test/settings.test.mjs
git commit -m "feat(web): settings localStorage 持久化"
```

---

## Task 4: 状态→符号决策（TDD，复用 v1.5.2 语义）

**Files:**
- Create: `docs/web/js/iconSymbol.js`
- Test: `docs/web/test/iconSymbol.test.mjs`

- [ ] **Step 1: 写失败测试**

`docs/web/test/iconSymbol.test.mjs`:
```js
import { test } from "node:test";
import assert from "node:assert";
import { iconSymbol } from "../js/iconSymbol.js";

const base = { present: true, sitMinutes: 0, sitMax: 45, evalResult: null };

test("无人 → away", () => {
  assert.strictEqual(iconSymbol({ ...base, present: false }), "away");
});
test("姿势好 → good", () => {
  assert.strictEqual(iconSymbol({ ...base, evalResult: { isBad: false, problems: [] } }), "good");
});
test("久坐优先于姿势偏 → clock", () => {
  assert.strictEqual(iconSymbol({ ...base, sitMinutes: 50,
    evalResult: { isBad: true, problems: ["head_tilt"], headTiltDir: 1 } }), "clock");
});
test("前倾 → arrow_up", () => {
  assert.strictEqual(iconSymbol({ ...base,
    evalResult: { isBad: true, problems: ["neck"] } }), "arrow_up");
});
test("头向右歪(dir=1) → arrow_left（该向左）", () => {
  assert.strictEqual(iconSymbol({ ...base,
    evalResult: { isBad: true, problems: ["head_tilt"], headTiltDir: 1 } }), "arrow_left");
});
test("左肩高(dir=1) → shoulder_left", () => {
  assert.strictEqual(iconSymbol({ ...base,
    evalResult: { isBad: true, problems: ["shoulder"], shoulderDir: 1 } }), "shoulder_left");
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `node --test docs/web/test/iconSymbol.test.mjs`
Expected: FAIL — 找不到模块

- [ ] **Step 3: 写 iconSymbol.js**

`docs/web/js/iconSymbol.js`:
```js
// 状态 → 符号决策。优先级：待机 > 久坐 > 姿势偏 > 好（与桌面版 v1.5.2 一致）
// 入参 { present, sitMinutes, sitMax, evalResult }
export function iconSymbol({ present, sitMinutes, sitMax, evalResult }) {
  if (!present) return "away";
  if (sitMinutes >= sitMax) return "clock";
  const r = evalResult;
  if (r && r.isBad) {
    if (r.problems.includes("neck") || r.problems.includes("torso")) return "arrow_up";
    if (r.problems.includes("head_tilt")) {
      return r.headTiltDir > 0 ? "arrow_left" : "arrow_right"; // +1头向右歪→该向左
    }
    if (r.problems.includes("shoulder")) {
      return r.shoulderDir > 0 ? "shoulder_left" : "shoulder_right"; // +1左肩高
    }
  }
  return "good";
}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `node --test docs/web/test/iconSymbol.test.mjs`
Expected: PASS（6 个测试）

- [ ] **Step 5: 提交**

```bash
git add docs/web/js/iconSymbol.js docs/web/test/iconSymbol.test.mjs
git commit -m "feat(web): 状态→符号决策（复用 v1.5.2 优先级与方向语义）"
```

---

## Task 5: camera 模块

**Files:**
- Create: `docs/web/js/camera.js`

- [ ] **Step 1: 写 camera.js**

`docs/web/js/camera.js`:
```js
// 打开摄像头并绑定到 video 元素。失败抛错由调用方处理。
export async function startCamera(videoEl) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("unsupported");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480, facingMode: "user" },
    audio: false,
  });
  videoEl.srcObject = stream;
  await videoEl.play();
  return stream;
}

export function stopCamera(stream) {
  if (stream) stream.getTracks().forEach((tk) => tk.stop());
}
```

- [ ] **Step 2: 提交**

```bash
git add docs/web/js/camera.js
git commit -m "feat(web): camera getUserMedia 封装"
```

---

## Task 6: detector 模块（MediaPipe PoseLandmarker）

**Files:**
- Create: `docs/web/js/detector.js`

- [ ] **Step 1: 写 detector.js**

`docs/web/js/detector.js`:
```js
import { PoseLandmarker, FilesetResolver }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

let landmarker = null;

// 加载模型（首次约几 MB，浏览器缓存后秒开）
export async function initDetector() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  landmarker = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numPoses: 1,
  });
}

// 检测一帧。返回 33 点 landmark 数组，或 null（无人）。
export function detect(videoEl, timestampMs) {
  if (!landmarker) return null;
  const res = landmarker.detectForVideo(videoEl, timestampMs);
  if (!res.landmarks || res.landmarks.length === 0) return null;
  return res.landmarks[0]; // [{x,y,z,visibility}, ...] 共 33 点
}
```

- [ ] **Step 2: 提交**

```bash
git add docs/web/js/detector.js
git commit -m "feat(web): detector 封装 MediaPipe PoseLandmarker"
```

---

## Task 7: overlay 模块（canvas 骨骼线 + 参考线）

**Files:**
- Create: `docs/web/js/overlay.js`

- [ ] **Step 1: 写 overlay.js**

`docs/web/js/overlay.js`:
```js
import { LM } from "./landmarks.js";

// 上半身骨骼连线（耳-肩-髋）
const BONES = [
  [LM.LEFT_EAR, LM.LEFT_SHOULDER], [LM.RIGHT_EAR, LM.RIGHT_SHOULDER],
  [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER],
  [LM.LEFT_SHOULDER, LM.LEFT_HIP], [LM.RIGHT_SHOULDER, LM.RIGHT_HIP],
  [LM.LEFT_HIP, LM.RIGHT_HIP],
];

// 在 canvas 上画骨骼线 + 水平/垂直参考线。
// lm 为 null 时只清空。color 由调用方按状态给（好=绿，差=橙）。
export function draw(ctx, w, h, lm, color) {
  ctx.clearRect(0, 0, w, h);
  if (!lm) return;
  const px = (p) => [p.x * w, p.y * h];

  // 骨骼线
  ctx.lineWidth = 4;
  ctx.strokeStyle = color;
  for (const [a, b] of BONES) {
    if (lm[a].visibility < 0.5 || lm[b].visibility < 0.5) continue;
    const [ax, ay] = px(lm[a]); const [bx, by] = px(lm[b]);
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
  }
  // 关键点
  ctx.fillStyle = color;
  for (const idx of [LM.LEFT_EAR, LM.RIGHT_EAR, LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER, LM.LEFT_HIP, LM.RIGHT_HIP]) {
    if (lm[idx].visibility < 0.5) continue;
    const [x, y] = px(lm[idx]);
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
  }
  // 参考线：肩中点垂直铅垂线（理想躯干）+ 肩水平线
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  if (ls.visibility >= 0.5 && rs.visibility >= 0.5) {
    const midx = (ls.x + rs.x) / 2 * w;
    const shy = (ls.y + rs.y) / 2 * h;
    ctx.setLineDash([6, 6]); ctx.lineWidth = 2; ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.beginPath(); ctx.moveTo(midx, shy - h * 0.1); ctx.lineTo(midx, shy + h * 0.4); ctx.stroke(); // 铅垂
    ctx.beginPath(); ctx.moveTo(ls.x * w, shy); ctx.lineTo(rs.x * w, shy); ctx.stroke();            // 肩水平基准
    ctx.setLineDash([]);
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add docs/web/js/overlay.js
git commit -m "feat(web): overlay canvas 骨骼线+参考线"
```

---

## Task 8: reminder 模块（防抖 + 通知/声音/标签页）

**Files:**
- Create: `docs/web/js/reminder.js`

- [ ] **Step 1: 写 reminder.js**

`docs/web/js/reminder.js`:
```js
import { t } from "./i18n.js";

// 用 Web Audio 生成一声短提示音（免音频文件）
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.frequency.value = 660; g.gain.value = 0.15;
    o.start(); o.stop(ctx.currentTime + 0.18);
  } catch { /* 忽略 */ }
}

let origTitle = null;
let origFavicon = null;

function setTabAlert(on) {
  if (origTitle === null) origTitle = document.title;
  const link = document.querySelector('link[rel="icon"]');
  if (origFavicon === null && link) origFavicon = link.href;
  if (on) {
    document.title = t("tab.alert");
    if (link) link.href = redDotFavicon();
  } else {
    document.title = origTitle;
    if (link && origFavicon) link.href = origFavicon;
  }
}

function redDotFavicon() {
  const c = document.createElement("canvas"); c.width = c.height = 32;
  const x = c.getContext("2d");
  x.fillStyle = "#E53935"; x.beginPath(); x.arc(16, 16, 14, 0, Math.PI * 2); x.fill();
  return c.toDataURL("image/png");
}

export async function requestNotifyPermission() {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const p = await Notification.requestPermission();
  return p === "granted";
}

// 防抖触发：bad 连续 BAD_STREAK 次才提醒，good 后清除标签页提醒。
const BAD_STREAK = 3;
let badCount = 0;
let lastNotify = 0;
const COOLDOWN_MS = 60_000;

// settings: {notify, sound, tab_alert}; message: 提醒文案
export function onState(isBad, message, settings) {
  if (!isBad) {
    badCount = 0;
    if (settings.tab_alert) setTabAlert(false);
    return;
  }
  badCount++;
  if (badCount < BAD_STREAK) return;

  const now = Date.now();
  if (settings.tab_alert) setTabAlert(true);
  if (now - lastNotify < COOLDOWN_MS) return;  // 通知/声音节流
  lastNotify = now;
  if (settings.sound) beep();
  if (settings.notify && "Notification" in window && Notification.permission === "granted") {
    new Notification(t("notify.title"), { body: message });
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add docs/web/js/reminder.js
git commit -m "feat(web): reminder 防抖 + 通知/声音/标签页提醒"
```

---

## Task 9: 页面 + 主循环 + 样式

**Files:**
- Create: `docs/web/index.html`
- Create: `docs/web/css/style.css`
- Create: `docs/web/js/app.js`

- [ ] **Step 1: 写 index.html**

`docs/web/index.html`:
```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>坐姿监控</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='14' fill='%234CAF50'/></svg>">
<link rel="stylesheet" href="css/style.css">
</head>
<body>
<main>
  <h1 id="title">坐姿监控</h1>
  <div id="stage">
    <video id="video" playsinline muted></video>
    <canvas id="overlay"></canvas>
  </div>
  <div id="statusbar">
    <span id="symbol">●</span>
    <span id="statusText">—</span>
    <span id="sitTimer"></span>
  </div>
  <div id="controls">
    <button id="startBtn">开始监控</button>
    <label><input type="checkbox" id="notifyChk" checked> 通知</label>
    <label><input type="checkbox" id="soundChk" checked> 声音</label>
    <select id="langSel"><option value="zh">中文</option><option value="en">English</option></select>
  </div>
  <p id="hint" class="hint"></p>
</main>
<script type="module" src="js/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 style.css**

`docs/web/css/style.css`:
```css
:root { --green:#4CAF50; --orange:#FF9800; --red:#E53935; --bg:#0d1117; --card:#161b22; --text:#e6edf3; --muted:#8b949e; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif; background:var(--bg); color:var(--text); display:flex; justify-content:center; padding:24px; }
main { width:100%; max-width:680px; text-align:center; }
h1 { font-size:1.4rem; margin-bottom:16px; }
#stage { position:relative; width:100%; aspect-ratio:4/3; background:var(--card); border-radius:12px; overflow:hidden; }
#video, #overlay { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; transform:scaleX(-1); } /* 镜像，自拍视角 */
#statusbar { display:flex; align-items:center; justify-content:center; gap:12px; margin:16px 0; font-size:1.2rem; }
#symbol { font-size:1.6rem; }
#controls { display:flex; gap:14px; align-items:center; justify-content:center; flex-wrap:wrap; }
button { background:var(--green); color:#fff; border:0; padding:10px 22px; border-radius:8px; font-size:1rem; cursor:pointer; }
button:disabled { opacity:.5; cursor:default; }
label, select { color:var(--muted); font-size:.9rem; }
.hint { color:var(--muted); margin-top:14px; font-size:.85rem; min-height:1.2em; }
.good { color:var(--green); } .warn { color:var(--orange); } .bad { color:var(--red); } .idle { color:var(--muted); }
```

- [ ] **Step 3: 写 app.js（主循环）**

`docs/web/js/app.js`:
```js
import { startCamera, stopCamera } from "./camera.js";
import { initDetector, detect } from "./detector.js";
import { evaluatePosture } from "./posture.js";
import { draw } from "./overlay.js";
import { onState, requestNotifyPermission } from "./reminder.js";
import { loadSettings, saveSettings } from "./settings.js";
import { iconSymbol } from "./iconSymbol.js";
import { t, setLang } from "./i18n.js";

const SYMBOL_CHAR = {
  good: "✓", away: "○", clock: "⏰",
  arrow_up: "↑", arrow_left: "←", arrow_right: "→",
  shoulder_left: "↘", shoulder_right: "↙",
};
const SYMBOL_CLASS = {
  good: "good", away: "idle", clock: "bad",
  arrow_up: "warn", arrow_left: "warn", arrow_right: "warn",
  shoulder_left: "warn", shoulder_right: "warn",
};
const PROBLEM_MSG = {
  arrow_left: "problem.head_left", arrow_right: "problem.head_right",
  arrow_up: "problem.forward",
  shoulder_left: "problem.shoulder_left", shoulder_right: "problem.shoulder_right",
  clock: "status.sit_long",
};

const video = document.getElementById("video");
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");
const startBtn = document.getElementById("startBtn");
const symbolEl = document.getElementById("symbol");
const statusEl = document.getElementById("statusText");
const sitTimerEl = document.getElementById("sitTimer");
const hintEl = document.getElementById("hint");

let settings = loadSettings();
let stream = null;
let running = false;
let sitStart = null;
let lastDetect = 0;
let lastEval = null;

function applyLang() {
  setLang(settings.lang);
  document.getElementById("title").textContent = t("app.title");
  startBtn.textContent = running ? t("btn.stop") : t("btn.start");
}

document.getElementById("notifyChk").checked = settings.notify;
document.getElementById("soundChk").checked = settings.sound;
document.getElementById("langSel").value = settings.lang;
applyLang();

document.getElementById("notifyChk").addEventListener("change", (e) => { settings.notify = e.target.checked; saveSettings(settings); });
document.getElementById("soundChk").addEventListener("change", (e) => { settings.sound = e.target.checked; saveSettings(settings); });
document.getElementById("langSel").addEventListener("change", (e) => { settings.lang = e.target.value; saveSettings(settings); applyLang(); });

startBtn.addEventListener("click", () => running ? stop() : start());

async function start() {
  hintEl.textContent = "";
  try {
    startBtn.disabled = true;
    await initDetector();
    stream = await startCamera(video);
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    if (settings.notify) await requestNotifyPermission();
    running = true; sitStart = Date.now();
    startBtn.disabled = false; applyLang();
    requestAnimationFrame(loop);
  } catch (err) {
    startBtn.disabled = false;
    hintEl.textContent = err.message === "unsupported" ? t("perm.unsupported") : t("perm.camera");
  }
}

function stop() {
  running = false;
  stopCamera(stream); stream = null;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  symbolEl.textContent = "○"; symbolEl.className = "idle";
  statusEl.textContent = "—"; sitTimerEl.textContent = "";
  applyLang();
}

function loop(ts) {
  if (!running) return;
  // 检测节流：约 1 秒一次
  if (ts - lastDetect >= 1000) {
    lastDetect = ts;
    const lm = detect(video, ts);
    const present = !!lm;
    lastEval = present ? evaluatePosture(lm, settings) : null;

    const sitMinutes = sitStart ? (Date.now() - sitStart) / 60000 : 0;
    const sym = iconSymbol({ present, sitMinutes, sitMax: settings.sit_max_minutes, evalResult: lastEval });

    // overlay 颜色：好=绿，差=橙，无人=灰
    const col = sym === "good" ? "#4CAF50" : sym === "away" ? "#8b949e" : "#FF9800";
    draw(ctx, canvas.width, canvas.height, lm, col);

    // 状态条
    symbolEl.textContent = SYMBOL_CHAR[sym]; symbolEl.className = SYMBOL_CLASS[sym];
    const msgKey = PROBLEM_MSG[sym];
    statusEl.textContent = present ? (msgKey ? t(msgKey) : t("status.good")) : t("status.away");
    sitTimerEl.textContent = present ? `${Math.floor(sitMinutes)}min` : "";

    // 提醒（久坐或姿势偏都算 bad）
    const isBad = sym !== "good" && sym !== "away";
    onState(isBad, statusEl.textContent, settings);
  }
  requestAnimationFrame(loop);
}
```

- [ ] **Step 4: 手动端到端测试**

```bash
# 项目根起本地 https/localhost 静态服务（getUserMedia 需安全上下文）
cd docs/web && python3 -m http.server 8000
```
浏览器开 `http://localhost:8000`，点「开始监控」：
- 授权摄像头 → 看到画面 + 镜像 + 骨骼线 + 参考线
- 坐直 → ✓ 绿、"姿势良好"
- 头向左歪 → → 箭头、"头向左歪，向右摆正"
- 前倾 → ↑、"身体前倾，坐直"
- 耸左肩 → 倾斜符号 + "左肩偏高"
- 切到别的标签等待 → 标签页标题变"⚠ 坐直！"、收到通知
- 拒绝摄像头 → 显示 `perm.camera` 提示
- 切换语言 → 文案更新

- [ ] **Step 5: 提交**

```bash
git add docs/web/index.html docs/web/css/style.css docs/web/js/app.js
git commit -m "feat(web): 监控台页面 + 主循环 + 状态条"
```

---

## Task 10: 落地页入口 + 部署

**Files:**
- Modify: `docs/index.html`（加「在线试用」按钮）

- [ ] **Step 1: 在落地页加入口**

在 `docs/index.html` 的主行动区（hero/下载区）插入一个按钮，链到 `web/`：
```html
<a href="web/" class="cta">▶ 在线试用（网页版）</a>
```
（按现有落地页的按钮 class 风格放置；若无现成 class，复用下载按钮的样式类。）

- [ ] **Step 2: 跑全部单元测试**

Run: `node --test docs/web/test/`
Expected: PASS（posture 7 + settings 3 + iconSymbol 6 = 16 个测试全过）

- [ ] **Step 3: 提交并推送（GitHub Pages 自动部署）**

```bash
git add docs/index.html
git commit -m "feat(web): 落地页加在线试用入口"
git push origin main && git push gitee main
```

- [ ] **Step 4: 线上验证**

GitHub Pages 部署后开 `https://<pages-domain>/web/`，重跑 Task 9 Step 4 的手测清单（https 下通知/摄像头应正常）。

---

## Self-Review

**Spec 覆盖检查：**
- 实时检测 → Task 6 detector ✅
- 监控台界面（画面+骨骼+参考线+状态条）→ Task 7 overlay + Task 9 ✅
- 4 类姿势问题 + 方向 → Task 1 posture + Task 4 iconSymbol ✅
- 久坐计时提醒 → Task 9 app.js sitMinutes + iconSymbol clock ✅
- 通知+声音+标签页 → Task 8 reminder ✅
- 设置 localStorage → Task 3 settings ✅
- i18n zh/en → Task 2 ✅
- 错误处理（摄像头拒绝/不支持/无人）→ Task 5 + Task 9 start() catch + away ✅
- 部署 docs/web + 落地页入口 → Task 10 ✅
- 复用 v1.5.2 符号语义 → Task 4 iconSymbol ✅
- 疲劳/历史/云同步 → 明确不在 MVP（Spec YAGNI）✅

**类型一致性：** evaluatePosture 返回 `{isBad, problems, details, shoulderDir, headTiltDir}` —
Task 4 iconSymbol 读 `evalResult.problems/headTiltDir/shoulderDir`，Task 9 读同名字段，一致 ✅

**占位符扫描：** 无 TBD/TODO；每个代码 step 都是完整可运行代码 ✅

**已知校准点：** video 用 `scaleX(-1)` 镜像（自拍视角）。左右方向若与体感相反，
翻转 iconSymbol 中 dir 判断即可（不影响其他模块）。
