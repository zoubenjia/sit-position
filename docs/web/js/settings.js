const KEY = "sitmonitor_web";

export const DEFAULTS = {
  shoulder: 10, neck: 28, torso: 8, head_tilt: 12,
  sit_max_minutes: 45,
  notify: true, sound: true, tab_alert: true,
  lang: "zh",
};

// 仅持久化用户在 UI 可改的偏好（notify/sound/tab_alert/lang）。
// 阈值始终取最新 DEFAULTS —— 网页版无改阈值入口，避免旧 localStorage
// 把阈值锁死在旧值（否则调整默认阈值对老用户不生效）。
export function loadSettings() {
  let saved = {};
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) saved = JSON.parse(raw);
  } catch {
    saved = {};
  }
  return {
    ...DEFAULTS,
    notify: saved.notify ?? DEFAULTS.notify,
    sound: saved.sound ?? DEFAULTS.sound,
    tab_alert: saved.tab_alert ?? DEFAULTS.tab_alert,
    lang: saved.lang ?? DEFAULTS.lang,
  };
}

export function saveSettings(s) {
  localStorage.setItem(KEY, JSON.stringify(s));
}
