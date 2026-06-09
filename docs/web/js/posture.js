import { LM } from "./landmarks.js";

// 向量 (dx, dy) 与垂直向上方向的夹角（度）
function angleDeg(dx, dy) {
  return Math.abs(Math.atan2(dx, -dy) * 180 / Math.PI);
}

// 肩膀倾斜角：正值=左肩高右肩低，负值=右肩高。可见度不足返回 null
export function shoulderTilt(lm) {
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  if (ls.visibility < 0.5 || rs.visibility < 0.5) return null;
  const dy = rs.y - ls.y;            // 正值=左肩高（图像 y 向下）
  const dx = Math.abs(rs.x - ls.x);
  if (dx < 0.001) return 0;
  return Math.atan2(dy, dx) * 180 / Math.PI;
}

// 头部左右侧倾：正值=左耳高（头向右歪），负值=右耳高（头向左歪）
export function headTilt(lm) {
  const le = lm[LM.LEFT_EAR], re = lm[LM.RIGHT_EAR];
  if (le.visibility < 0.5 || re.visibility < 0.5) return null;
  const dy = re.y - le.y;            // 正值=左耳高
  const dx = Math.abs(re.x - le.x);
  if (dx < 0.001) return 0;
  return Math.atan2(dy, dx) * 180 / Math.PI;
}

// 头部前倾角：耳-肩连线与垂直线夹角，取左右平均
export function headForwardAngle(lm) {
  const le = lm[LM.LEFT_EAR], re = lm[LM.RIGHT_EAR];
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  const a = [];
  if (le.visibility >= 0.5 && ls.visibility >= 0.5) a.push(angleDeg(le.x - ls.x, le.y - ls.y));
  if (re.visibility >= 0.5 && rs.visibility >= 0.5) a.push(angleDeg(re.x - rs.x, re.y - rs.y));
  return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
}

// 躯干前倾角：肩-髋连线与垂直线夹角，取左右平均
export function torsoForwardAngle(lm) {
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  const lh = lm[LM.LEFT_HIP], rh = lm[LM.RIGHT_HIP];
  const a = [];
  if (ls.visibility >= 0.5 && lh.visibility >= 0.5) a.push(angleDeg(ls.x - lh.x, ls.y - lh.y));
  if (rs.visibility >= 0.5 && rh.visibility >= 0.5) a.push(angleDeg(rs.x - rh.x, rs.y - rh.y));
  return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
}

// 综合判定。thresholds: {shoulder, neck, torso, head_tilt}
// 返回 { isBad, problems:[], details:{}, shoulderDir, headTiltDir }
export function evaluatePosture(lm, thr) {
  const st = shoulderTilt(lm);
  const ht = headTilt(lm);
  const hf = headForwardAngle(lm);
  const tf = torsoForwardAngle(lm);
  const problems = [];
  const details = { shoulder: st, head_tilt: ht, neck: hf, torso: tf };

  if (st !== null && Math.abs(st) > thr.shoulder) problems.push("shoulder");
  if (ht !== null && Math.abs(ht) > thr.head_tilt) problems.push("head_tilt");
  if (hf !== null && hf > thr.neck) problems.push("neck");
  if (tf !== null && tf > thr.torso) problems.push("torso");

  return {
    isBad: problems.length > 0,
    problems,
    details,
    shoulderDir: st === null ? 0 : (st > 0 ? 1 : -1),
    headTiltDir: ht === null ? 0 : (ht > 0 ? 1 : -1),
  };
}
