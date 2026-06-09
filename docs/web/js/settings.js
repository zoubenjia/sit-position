const KEY = "sitmonitor_web";

export const DEFAULTS = {
  shoulder: 10, neck: 20, torso: 8, head_tilt: 12,
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
