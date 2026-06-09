import { LM } from "./landmarks.js";

const BONES = [
  [LM.LEFT_EAR, LM.LEFT_SHOULDER], [LM.RIGHT_EAR, LM.RIGHT_SHOULDER],
  [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER],
  [LM.LEFT_SHOULDER, LM.LEFT_HIP], [LM.RIGHT_SHOULDER, LM.RIGHT_HIP],
  [LM.LEFT_HIP, LM.RIGHT_HIP],
];

// 在 canvas 上画骨骼线 + 水平/垂直参考线。lm 为 null 时只清空。
export function draw(ctx, w, h, lm, color) {
  ctx.clearRect(0, 0, w, h);
  if (!lm) return;
  const px = (p) => [p.x * w, p.y * h];

  ctx.lineWidth = 4;
  ctx.strokeStyle = color;
  for (const [a, b] of BONES) {
    if (lm[a].visibility < 0.5 || lm[b].visibility < 0.5) continue;
    const [ax, ay] = px(lm[a]); const [bx, by] = px(lm[b]);
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
  }
  ctx.fillStyle = color;
  for (const idx of [LM.LEFT_EAR, LM.RIGHT_EAR, LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER, LM.LEFT_HIP, LM.RIGHT_HIP]) {
    if (lm[idx].visibility < 0.5) continue;
    const [x, y] = px(lm[idx]);
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
  }
  const ls = lm[LM.LEFT_SHOULDER], rs = lm[LM.RIGHT_SHOULDER];
  if (ls.visibility >= 0.5 && rs.visibility >= 0.5) {
    const midx = (ls.x + rs.x) / 2 * w;
    const shy = (ls.y + rs.y) / 2 * h;
    ctx.setLineDash([6, 6]); ctx.lineWidth = 2; ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.beginPath(); ctx.moveTo(midx, shy - h * 0.1); ctx.lineTo(midx, shy + h * 0.4); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ls.x * w, shy); ctx.lineTo(rs.x * w, shy); ctx.stroke();
    ctx.setLineDash([]);
  }
}
