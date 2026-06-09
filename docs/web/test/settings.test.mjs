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
