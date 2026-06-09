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
  if (ts - lastDetect >= 1000) {
    lastDetect = ts;
    const lm = detect(video, ts);
    const present = !!lm;
    lastEval = present ? evaluatePosture(lm, settings) : null;

    const sitMinutes = sitStart ? (Date.now() - sitStart) / 60000 : 0;
    const sym = iconSymbol({ present, sitMinutes, sitMax: settings.sit_max_minutes, evalResult: lastEval });

    const col = sym === "good" ? "#4CAF50" : sym === "away" ? "#8b949e" : "#FF9800";
    draw(ctx, canvas.width, canvas.height, lm, col);

    symbolEl.textContent = SYMBOL_CHAR[sym]; symbolEl.className = SYMBOL_CLASS[sym];
    const msgKey = PROBLEM_MSG[sym];
    statusEl.textContent = present ? (msgKey ? t(msgKey) : t("status.good")) : t("status.away");
    sitTimerEl.textContent = present ? `${Math.floor(sitMinutes)}min` : "";

    const isBad = sym !== "good" && sym !== "away";
    onState(isBad, statusEl.textContent, settings);
  }
  requestAnimationFrame(loop);
}
