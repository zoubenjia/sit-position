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
