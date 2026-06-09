"""动态生成托盘图标 — 根据具体姿势问题显示不同侧视坐姿人形。

问题类型:
  neck       - 颈部前倾
  head_tilt  - 头部侧倾
  shoulder   - 肩膀不平
  torso      - 躯干前倾
"""

import os
import tempfile
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

# 问题类型常量
NECK = "neck"
HEAD_TILT = "head_tilt"
SHOULDER = "shoulder"
TORSO = "torso"

# 颜色 (RGBA)
_GREEN = (76, 175, 80, 255)
_ORANGE = (255, 152, 0, 255)
_RED = (229, 57, 53, 255)
_GRAY = (158, 158, 158, 255)
_BLUE = (33, 150, 243, 255)        # 运动模式蓝色
_HIGHLIGHT = (255, 255, 100, 220)  # 黄色高亮标记

# 缓存
_path_cache: Dict[Tuple, str] = {}
_img_cache: Dict[Tuple, Image.Image] = {}
_tmp_dir: Optional[str] = None


def _tmp():
    global _tmp_dir
    if _tmp_dir is None:
        _tmp_dir = tempfile.mkdtemp(prefix="sit_icons_")
    return _tmp_dir


def _severity_color(problems: List[str]) -> Tuple[int, ...]:
    if len(problems) >= 2:
        return _RED
    return _ORANGE


def _draw_figure(draw: ImageDraw.Draw, size: int,
                 problems: List[str], color: Tuple[int, ...]):
    """在 size×size 透明画布上绘制侧视坐姿人形。"""
    s = size / 44.0
    lw = max(2, round(3 * s))
    thin = max(1, round(2 * s))

    def pt(x, y):
        return (round(x * s), round(y * s))

    # ── 基准坐标（正确坐姿, 44px 参考画布）──
    head_cx, head_cy, head_r = 20.0, 8.0, 5.5
    sh_x, sh_y = 18.0, 18.0     # 肩膀
    hip_x, hip_y = 22.0, 30.0
    knee_x, knee_y = 31.0, 30.0
    foot_x, foot_y = 31.0, 40.0

    # ── 姿势变形 ──
    if NECK in problems:
        head_cx += 8
        head_cy += 2
    if TORSO in problems:
        sh_x += 5
        sh_y += 2
        head_cx += 3
    if HEAD_TILT in problems:
        head_cy += 3
    if SHOULDER in problems:
        sh_y += 2

    # ── 椅子（半透明）──
    chair = (*color[:3], 90)
    draw.line([pt(12, 17), pt(12, 34)], fill=chair, width=thin)   # 椅背
    draw.line([pt(12, 34), pt(35, 34)], fill=chair, width=thin)   # 椅座
    draw.line([pt(12, 34), pt(10, 43)], fill=chair, width=thin)   # 后腿
    draw.line([pt(35, 34), pt(37, 43)], fill=chair, width=thin)   # 前腿

    # ── 人体 ──
    draw.line([pt(hip_x, hip_y), pt(sh_x, sh_y)], fill=color, width=lw)         # 躯干
    draw.line([pt(hip_x, hip_y), pt(knee_x, knee_y)], fill=color, width=lw)     # 大腿
    draw.line([pt(knee_x, knee_y), pt(foot_x, foot_y)], fill=color, width=lw)   # 小腿
    draw.line([pt(sh_x, sh_y), pt(head_cx, head_cy + head_r)], fill=color, width=lw)  # 颈部

    # 头部
    draw.ellipse([pt(head_cx - head_r, head_cy - head_r),
                  pt(head_cx + head_r, head_cy + head_r)], fill=color)

    # ── 问题高亮标记（@2x 可见）──
    hi = _HIGHLIGHT

    if NECK in problems:
        # 头前方小箭头 →
        ax = head_cx + head_r + 1
        ay = head_cy
        draw.line([pt(ax, ay), pt(ax + 5, ay)], fill=hi, width=thin)
        draw.line([pt(ax + 3, ay - 2), pt(ax + 5, ay)], fill=hi, width=thin)
        draw.line([pt(ax + 3, ay + 2), pt(ax + 5, ay)], fill=hi, width=thin)

    if SHOULDER in problems:
        # 肩部波浪 ~
        sy = sh_y
        draw.line([pt(sh_x - 5, sy - 1), pt(sh_x - 3, sy + 1),
                   pt(sh_x - 1, sy - 1)], fill=hi, width=thin)

    if HEAD_TILT in problems:
        # 头旁倾斜标记 /
        tx = head_cx - head_r - 2
        draw.line([pt(tx, head_cy - 3), pt(tx - 3, head_cy + 3)], fill=hi, width=thin)

    if TORSO in problems:
        # 背部弧线标记 )
        mx = (sh_x + hip_x) / 2 - 3
        my = (sh_y + hip_y) / 2
        draw.line([pt(mx, my - 4), pt(mx - 2, my), pt(mx, my + 4)], fill=hi, width=thin)


def _draw_pushup(draw: ImageDraw.Draw, size: int, color: Tuple[int, ...]):
    """在 size×size 透明画布上绘制侧视俯卧撑人形。"""
    s = size / 44.0
    lw = max(2, round(3 * s))
    thin = max(1, round(2 * s))

    def pt(x, y):
        return (round(x * s), round(y * s))

    # ── 地面 ──
    ground_y = 38.0
    draw.line([pt(2, ground_y), pt(42, ground_y)], fill=(*color[:3], 60), width=thin)

    # ── 人体（俯卧撑姿势，面朝左）──
    head_cx, head_cy, head_r = 6.0, 19.0, 4.5   # 头部（左侧）
    hand_x, hand_y = 10.0, ground_y              # 手掌撑地
    sh_x, sh_y = 12.0, 22.0                      # 肩膀
    hip_x, hip_y = 28.0, 24.0                    # 髋部
    foot_x, foot_y = 40.0, ground_y              # 脚尖着地

    # 手臂（手→肩）
    draw.line([pt(hand_x, hand_y), pt(sh_x, sh_y)], fill=color, width=lw)
    # 躯干（肩→髋）
    draw.line([pt(sh_x, sh_y), pt(hip_x, hip_y)], fill=color, width=lw)
    # 腿（髋→脚）
    draw.line([pt(hip_x, hip_y), pt(foot_x, foot_y)], fill=color, width=lw)
    # 颈部（肩→头）
    draw.line([pt(sh_x, sh_y), pt(head_cx + head_r, head_cy)], fill=color, width=lw)
    # 头部
    draw.ellipse([pt(head_cx - head_r, head_cy - head_r),
                  pt(head_cx + head_r, head_cy + head_r)], fill=color)

    # ── 动感标记（上下箭头表示运动）──
    hi = _HIGHLIGHT
    mx = (sh_x + hip_x) / 2
    draw.line([pt(mx, sh_y - 8), pt(mx, sh_y - 4)], fill=hi, width=thin)
    draw.line([pt(mx - 2, sh_y - 6), pt(mx, sh_y - 8)], fill=hi, width=thin)
    draw.line([pt(mx + 2, sh_y - 6), pt(mx, sh_y - 8)], fill=hi, width=thin)


def generate(size: int, state: str = "good",
             problems: List[str] = None) -> Image.Image:
    """生成 RGBA 图标。"""
    problems = problems or []
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if state == "exercise":
        _draw_pushup(d, size, _BLUE)
    elif state in ("away", "stopped", "camera_wait"):
        _draw_figure(d, size, [], _GRAY)
    elif state == "camera_adjust":
        _draw_figure(d, size, [], _ORANGE)
    elif problems:
        _draw_figure(d, size, problems, _severity_color(problems))
    else:
        _draw_figure(d, size, [], _GREEN)

    return img


# ── 单符号占满图标（菜单栏 22px 也清晰）──
# 每个状态用一个截然不同的大符号，砍掉小人细节换辨识度：
#   good=绿对勾  arrow_*=橙纠正箭头  shoulder=橙倾斜线
#   clock=红时钟(久坐)  moon=红月亮(疲劳)  exercise=蓝俯卧撑  gray=灰待机环

_SYM_COLOR = {
    "good": _GREEN,
    "arrow_left": _ORANGE, "arrow_right": _ORANGE, "arrow_up": _ORANGE,
    "shoulder": _ORANGE, "shoulder_left": _ORANGE, "shoulder_right": _ORANGE,
    "clock": _RED, "moon": _RED,
    "exercise": _BLUE,
    "gray": _GRAY,
}


def _sp(s, x, y):
    return (round(x * s), round(y * s))


def _sym_check(d, s, color, w):
    d.line([_sp(s, 9, 24), _sp(s, 18, 33)], fill=color, width=w)
    d.line([_sp(s, 18, 33), _sp(s, 35, 11)], fill=color, width=w)


def _sym_arrow(d, s, direction, color, w):
    cx, cy, L, h = 22.0, 22.0, 15.0, 8.0
    if direction == "arrow_right":
        a, b = (cx - L, cy), (cx + L, cy)
        d.line([_sp(s, *a), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] - h, b[1] - h), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] - h, b[1] + h), _sp(s, *b)], fill=color, width=w)
    elif direction == "arrow_left":
        a, b = (cx + L, cy), (cx - L, cy)
        d.line([_sp(s, *a), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] + h, b[1] - h), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] + h, b[1] + h), _sp(s, *b)], fill=color, width=w)
    elif direction == "arrow_up":
        a, b = (cx, cy + L), (cx, cy - L)
        d.line([_sp(s, *a), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] - h, b[1] + h), _sp(s, *b)], fill=color, width=w)
        d.line([_sp(s, b[0] + h, b[1] + h), _sp(s, *b)], fill=color, width=w)


def _sym_shoulder(d, s, color, w, thin, high_side="right"):
    if high_side == "left":
        d.line([_sp(s, 8, 14), _sp(s, 36, 27)], fill=color, width=w)   # 左肩高 \
    else:
        d.line([_sp(s, 8, 27), _sp(s, 36, 14)], fill=color, width=w)   # 右肩高 /
    for x in range(8, 37, 6):                                          # 水平基准虚线
        d.line([_sp(s, x, 34), _sp(s, x + 3, 34)], fill=color, width=thin)


def _sym_clock(d, s, color, w):
    cx, cy, r = 22.0, 22.0, 15.0
    d.ellipse([_sp(s, cx - r, cy - r), _sp(s, cx + r, cy + r)], outline=color, width=w)
    d.line([_sp(s, cx, cy), _sp(s, cx, cy - 9)], fill=color, width=w)
    d.line([_sp(s, cx, cy), _sp(s, cx + 7, cy)], fill=color, width=w)


def _sym_moon(d, s, color):
    cx, cy, r = 24.0, 22.0, 15.0
    d.ellipse([_sp(s, cx - r, cy - r), _sp(s, cx + r, cy + r)], fill=color)
    d.ellipse([_sp(s, cx - r + 6, cy - r - 3), _sp(s, cx + r + 6, cy + r - 3)],
              fill=(0, 0, 0, 0))


def _sym_idle(d, s, w):
    cx, cy, r = 22.0, 22.0, 11.0
    d.ellipse([_sp(s, cx - r, cy - r), _sp(s, cx + r, cy + r)], outline=_GRAY, width=w)


def generate_symbol(size: int, symbol: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 44.0
    w = max(2, round(4 * s))
    thin = max(1, round(2 * s))
    color = _SYM_COLOR.get(symbol, _GRAY)
    if symbol == "good":
        _sym_check(d, s, color, w + 1)
    elif symbol in ("arrow_left", "arrow_right", "arrow_up"):
        _sym_arrow(d, s, symbol, color, w + 1)
    elif symbol == "shoulder_left":
        _sym_shoulder(d, s, color, w + 1, thin, "left")
    elif symbol in ("shoulder_right", "shoulder"):
        _sym_shoulder(d, s, color, w + 1, thin, "right")
    elif symbol == "clock":
        _sym_clock(d, s, color, w)
    elif symbol == "moon":
        _sym_moon(d, s, color)
    elif symbol == "exercise":
        _draw_pushup(d, size, _BLUE)
    else:
        _sym_idle(d, s, w)
    return img


_sym_path_cache: Dict[str, str] = {}


def symbol_path(symbol: str) -> str:
    """生成单符号图标并返回 1x PNG 路径（同目录生成 @2x 供 rumps）。"""
    if symbol in _sym_path_cache:
        return _sym_path_cache[symbol]
    d = _tmp()
    p1 = os.path.join(d, f"sym_{symbol}.png")
    p2 = os.path.join(d, f"sym_{symbol}@2x.png")
    generate_symbol(22, symbol).save(p1)
    generate_symbol(44, symbol).save(p2)
    _sym_path_cache[symbol] = p1
    return p1


# ── macOS (rumps) 接口：返回文件路径 ──

def icon_path(state: str = "good", problems: List[str] = None) -> str:
    """生成图标并返回 1x PNG 路径。同目录自动生成 @2x 版本供 rumps 加载。"""
    problems = problems or []
    key = (state, tuple(sorted(problems)))
    if key in _path_cache:
        return _path_cache[key]

    tag = "_".join(sorted(problems)) if problems else state
    d = _tmp()
    p1x = os.path.join(d, f"icon_{tag}.png")
    p2x = os.path.join(d, f"icon_{tag}@2x.png")

    generate(22, state, problems).save(p1x)
    generate(44, state, problems).save(p2x)

    _path_cache[key] = p1x
    return p1x


# ── Windows (pystray) 接口：返回 Image 对象 ──

def icon_image(state: str = "good", problems: List[str] = None,
               size: int = 64) -> Image.Image:
    """生成图标 Image 对象。"""
    problems = problems or []
    key = (state, tuple(sorted(problems)), size)
    if key in _img_cache:
        return _img_cache[key].copy()

    img = generate(size, state, problems)
    _img_cache[key] = img
    return img.copy()
