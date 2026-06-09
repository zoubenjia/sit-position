import { test, beforeEach } from "node:test";
import assert from "node:assert";

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

test("saveSettings + loadSettings: UI 偏好往返一致", () => {
  saveSettings({ ...DEFAULTS, lang: "en", sound: false });
  const s = loadSettings();
  assert.strictEqual(s.lang, "en");
  assert.strictEqual(s.sound, false);
});

test("loadSettings: 阈值始终取 DEFAULTS，不被旧缓存锁死", () => {
  saveSettings({ ...DEFAULTS, neck: 99, shoulder: 99 });
  const s = loadSettings();
  assert.strictEqual(s.neck, DEFAULTS.neck);
  assert.strictEqual(s.shoulder, DEFAULTS.shoulder);
});

test("loadSettings: 损坏 JSON 回退默认值", () => {
  localStorage.setItem("sitmonitor_web", "{not json");
  const s = loadSettings();
  assert.strictEqual(s.shoulder, DEFAULTS.shoulder);
});
