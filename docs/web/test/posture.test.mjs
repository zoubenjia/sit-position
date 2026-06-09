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
  const lm = lms({ 7: { x: 0.4, y: 0.25 }, 8: { x: 0.6, y: 0.45 },
                   11: { x: 0.4, y: 0.5 }, 12: { x: 0.6, y: 0.5 },
                   23: { x: 0.4, y: 0.8 }, 24: { x: 0.6, y: 0.8 } });
  const thr = { shoulder: 10, neck: 20, torso: 8, head_tilt: 12 };
  const r = evaluatePosture(lm, thr);
  assert.ok(r.problems.includes("head_tilt"));
  assert.strictEqual(r.headTiltDir, 1);
});
