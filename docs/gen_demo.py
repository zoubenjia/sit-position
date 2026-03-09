"""生成落地页 demo 动画 GIF — 展示图标状态变化流程"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw, ImageFont
from sit_monitor.icon_gen import generate, _GREEN, _ORANGE, _RED, _GRAY

# ── 配置 ──
W, H = 800, 420
BG = (13, 17, 23)           # 深色背景
BAR_H = 32                   # 模拟菜单栏高度
BAR_BG = (30, 30, 30)
ICON_LARGE = 160             # 中央大图标尺寸
FPS_MS = 1200                # 每帧停留毫秒

# 字体
def _font(size):
    paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

font_label = _font(28)
font_small = _font(18)
font_bar = _font(13)

# ── 帧定义 ──
# (state, problems, 中央标签, 状态提示, 菜单栏图标颜色说明)
FRAMES = [
    ("good",  [],                   "姿势良好",     "肩膀 2° · 颈部 14° · 躯干 5°",   "绿色 = 一切正常"),
    ("good",  [],                   "姿势良好",     "肩膀 3° · 颈部 13° · 躯干 4°",   "绿色 = 一切正常"),
    ("bad",   ["neck"],             "颈部前倾",     "颈部 28° 超出阈值 15°",           "橙色 = 单项问题"),
    ("bad",   ["neck"],             "颈部前倾",     "持续 30 秒... 发送提醒",          "橙色 = 单项问题"),
    ("bad",   ["neck", "shoulder"], "颈部前倾 + 肩膀不平", "颈部 26° · 肩膀 14°",    "红色 = 多项问题"),
    ("bad",   ["neck", "shoulder"], "颈部前倾 + 肩膀不平", "请纠正坐姿！",            "红色 = 多项问题"),
    ("good",  [],                   "姿势已纠正",   "\"坐姿很好，继续保持\"",           "绿色 = 恢复正常"),
    ("good",  [],                   "姿势良好",     "继续监控中...",                    "绿色 = 一切正常"),
]


def _color_for(state, problems):
    if state == "good":
        return _GREEN
    if len(problems) >= 2:
        return _RED
    return _ORANGE


def draw_frame(state, problems, label, hint, bar_hint):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    color = _color_for(state, problems)
    color_rgb = color[:3]

    # ── 模拟菜单栏 ──
    draw.rectangle([(0, 0), (W, BAR_H)], fill=BAR_BG)

    # 菜单栏左侧模拟项
    bar_items = ["Sit Monitor", "File", "Edit", "View"]
    bx = 16
    for i, item in enumerate(bar_items):
        c = (255, 255, 255) if i == 0 else (160, 160, 160)
        draw.text((bx, 8), item, fill=c, font=font_bar)
        bx += font_bar.getlength(item) + 20

    # 菜单栏右侧小图标
    icon_small = generate(22, state, problems)
    icon_small_rgb = Image.new("RGB", icon_small.size, BAR_BG)
    icon_small_rgb.paste(icon_small, mask=icon_small.split()[3])
    img.paste(icon_small_rgb, (W - 60, 5))

    # 右侧时间
    draw.text((W - 40, 8), "3:30", fill=(160, 160, 160), font=font_bar)

    # ── 中央大图标 ──
    icon_big = generate(ICON_LARGE, state, problems)
    icon_x = (W - ICON_LARGE) // 2
    icon_y = BAR_H + 40
    # 绘制圆角背景
    pad = 20
    bg_rect = [icon_x - pad, icon_y - pad, icon_x + ICON_LARGE + pad, icon_y + ICON_LARGE + pad]
    draw.rounded_rectangle(bg_rect, radius=20, fill=(22, 27, 34))
    # 贴图标
    icon_rgb = Image.new("RGB", icon_big.size, (22, 27, 34))
    icon_rgb.paste(icon_big, mask=icon_big.split()[3])
    img.paste(icon_rgb, (icon_x, icon_y))

    # ── 状态指示条 ──
    bar_y = icon_y + ICON_LARGE + pad + 16
    bar_w = 200
    bar_x = (W - bar_w) // 2
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 6)], radius=3, fill=(40, 40, 40))
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 6)], radius=3, fill=color_rgb)

    # ── 标签文字 ──
    text_y = bar_y + 20
    bbox = font_label.getbbox(label)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, text_y), label, fill=color_rgb, font=font_label)

    # ── 提示文字 ──
    hint_y = text_y + 40
    bbox2 = font_small.getbbox(hint)
    hw = bbox2[2] - bbox2[0]
    draw.text(((W - hw) // 2, hint_y), hint, fill=(139, 148, 158), font=font_small)

    # ── 底部图标颜色说明 ──
    note_y = H - 36
    bbox3 = font_small.getbbox(bar_hint)
    nw = bbox3[2] - bbox3[0]
    draw.text(((W - nw) // 2, note_y), bar_hint, fill=(100, 100, 100), font=font_small)

    return img


def main():
    frames = []
    for state, problems, label, hint, bar_hint in FRAMES:
        frames.append(draw_frame(state, problems, label, hint, bar_hint))

    out = os.path.join(os.path.dirname(__file__), "demo.gif")
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=FPS_MS,
        loop=0,
        optimize=True,
    )
    print(f"生成: {out} ({os.path.getsize(out) // 1024} KB, {len(frames)} 帧)")


if __name__ == "__main__":
    main()
