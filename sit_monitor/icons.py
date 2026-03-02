"""Pillow 生成系统托盘图标（彩色圆点）"""

from PIL import Image, ImageDraw

_SIZE = 64


def _make_circle(color):
    """生成指定颜色的圆点图标"""
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse([margin, margin, _SIZE - margin, _SIZE - margin], fill=color)
    return img


def green():
    return _make_circle((0, 200, 0, 255))


def red():
    return _make_circle((220, 40, 40, 255))


def gray():
    return _make_circle((140, 140, 140, 255))
