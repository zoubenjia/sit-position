// 状态 → 符号决策。优先级：待机 > 久坐 > 姿势偏 > 好（与桌面版 v1.5.2 一致）
export function iconSymbol({ present, sitMinutes, sitMax, evalResult }) {
  if (!present) return "away";
  if (sitMinutes >= sitMax) return "clock";
  const r = evalResult;
  if (r && r.isBad) {
    if (r.problems.includes("neck") || r.problems.includes("torso")) return "arrow_up";
    if (r.problems.includes("head_tilt")) {
      return r.headTiltDir > 0 ? "arrow_left" : "arrow_right";
    }
    if (r.problems.includes("shoulder")) {
      return r.shoulderDir > 0 ? "shoulder_left" : "shoulder_right";
    }
  }
  return "good";
}
