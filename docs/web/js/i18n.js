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
