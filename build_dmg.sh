#!/usr/bin/env bash
# 生成 SitMonitor.dmg 安装镜像
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/SitMonitor.app"
DMG="dist/SitMonitor.dmg"
VOL_NAME="SitMonitor"
STAGING="dist/dmg-staging"

if [ ! -d "$APP" ]; then
    echo "[!] 找不到 $APP，请先运行 build_app.sh"
    exit 1
fi

echo "=== 生成 DMG 安装镜像 ==="

# 清理
rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"

# 复制 App 和创建 Applications 快捷方式
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# 创建 DMG
echo "[*] 创建 DMG..."
hdiutil create -volname "$VOL_NAME" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG"

# 清理临时目录
rm -rf "$STAGING"

SIZE=$(du -sh "$DMG" | cut -f1)
echo ""
echo "=== DMG 生成成功 ==="
echo "  路径: $DMG"
echo "  大小: $SIZE"
echo ""
echo "安装方法: 双击 DMG，将 SitMonitor 拖入 Applications"
