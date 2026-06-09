import { t } from "./i18n.js";

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

const BAD_STREAK = 3;
let badCount = 0;
let lastNotify = 0;
const COOLDOWN_MS = 60_000;

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
  if (now - lastNotify < COOLDOWN_MS) return;
  lastNotify = now;
  if (settings.sound) beep();
  if (settings.notify && "Notification" in window && Notification.permission === "granted") {
    new Notification(t("notify.title"), { body: message });
  }
}
