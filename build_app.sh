#!/usr/bin/env bash
# 构建 SitMonitor.app
set -euo pipefail
cd "$(dirname "$0")"

# 激活 venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=== SitMonitor macOS App 构建 ==="

# 1. 检查 PyInstaller
if ! python -m PyInstaller --version &>/dev/null; then
    echo "[!] PyInstaller 未安装，正在安装..."
    uv pip install pyinstaller
fi

# 2. 生成 .icns 图标（如果有源文件）
ICON_SRC="build-resources/SitMonitor.png"
ICON_DST="build-resources/SitMonitor.icns"
if [ -f "$ICON_SRC" ] && ! [ -f "$ICON_DST" ]; then
    echo "[*] 生成 .icns 图标..."
    ICONSET="build-resources/SitMonitor.iconset"
    mkdir -p "$ICONSET"
    for sz in 16 32 64 128 256 512; do
        sips -z $sz $sz "$ICON_SRC" --out "$ICONSET/icon_${sz}x${sz}.png" &>/dev/null
        double=$((sz * 2))
        sips -z $double $double "$ICON_SRC" --out "$ICONSET/icon_${sz}x${sz}@2x.png" &>/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$ICON_DST"
    rm -rf "$ICONSET"
    echo "    -> $ICON_DST"
else
    [ -f "$ICON_DST" ] && echo "[*] 使用已有图标: $ICON_DST" \
                       || echo "[*] 无自定义图标，将使用默认图标"
fi

# 3. 检查必需资源
echo "[*] 检查资源文件..."
for f in pose_landmarker_lite.task face_landmarker.task; do
    if [ ! -f "$f" ]; then
        echo "[!] 缺少 $f，请先下载模型文件"
        exit 1
    fi
done
echo "    ML 模型 ✓"
echo "    Assets: $(ls sit_monitor/assets/*.png | wc -l | tr -d ' ') 个图标 ✓"

# 4. 清理旧构建
echo "[*] 清理旧构建..."
rm -rf build/SitMonitor dist/SitMonitor dist/SitMonitor.app

# 5. PyInstaller 打包
echo "[*] 开始 PyInstaller 打包..."
python -m PyInstaller SitMonitor.spec --noconfirm

# 6. 验证
APP="dist/SitMonitor.app"
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo ""
    echo "=== 构建成功 ==="
    echo "  路径: $APP"
    echo "  大小: $SIZE"
    echo ""
    echo "测试运行: open $APP"
else
    echo "[!] 构建失败：$APP 未生成"
    exit 1
fi
