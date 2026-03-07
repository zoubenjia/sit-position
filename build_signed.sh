#!/usr/bin/env bash
# 构建、签名、公证 SitMonitor.app 并生成 DMG
set -euo pipefail
cd "$(dirname "$0")"

IDENTITY="Developer ID Application: Benjia Zou (Z7GYVJPHBQ)"
KEYCHAIN_PROFILE="SitMonitor"
ENTITLEMENTS="build-resources/entitlements.plist"
APP="dist/SitMonitor.app"
DMG="dist/SitMonitor.dmg"

echo "=== SitMonitor 签名+公证构建 ==="

# 1. 构建 App（如果已有可跳过）
if [ "${SKIP_BUILD:-}" != "1" ]; then
    echo "[1/6] 构建 App..."
    bash build_app.sh
fi

if [ ! -d "$APP" ]; then
    echo "[!] $APP 不存在"
    exit 1
fi

# 2. 签名所有可执行内容（由内向外）
echo "[2/6] 代码签名..."

SIGN_COUNT=0
SIGN_FAIL=0

# 签名所有 .so .dylib 和 framework 里的二进制
while IFS= read -r -d '' f; do
    if codesign --force --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" --timestamp "$f" 2>/dev/null; then
        SIGN_COUNT=$((SIGN_COUNT + 1))
    else
        SIGN_FAIL=$((SIGN_FAIL + 1))
    fi
    if [ $((SIGN_COUNT % 50)) -eq 0 ] && [ $SIGN_COUNT -gt 0 ]; then
        echo "    已签名 $SIGN_COUNT 个..."
    fi
done < <(find "$APP/Contents" -type f \( -name "*.so" -o -name "*.dylib" -o -name "Python" -o -name "python*" \) -print0 2>/dev/null)

# 签名所有 .framework bundles
while IFS= read -r -d '' fw; do
    codesign --force --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" --timestamp "$fw" 2>/dev/null && SIGN_COUNT=$((SIGN_COUNT + 1)) || true
done < <(find "$APP/Contents" -type d -name "*.framework" -print0 2>/dev/null)

echo "    已签名 $SIGN_COUNT 个内部组件 (跳过 $SIGN_FAIL)"

# 签名主 app bundle
codesign --force --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" --timestamp "$APP"
echo "    App bundle 签名完成 ✓"

# 验证
codesign --verify --strict "$APP" 2>&1
echo "    签名验证通过 ✓"

# 3. 生成 DMG
echo "[3/6] 生成 DMG..."
rm -rf dist/dmg-staging "$DMG"
mkdir -p dist/dmg-staging
cp -R "$APP" dist/dmg-staging/
ln -s /Applications dist/dmg-staging/Applications
hdiutil create -volname "SitMonitor" \
    -srcfolder dist/dmg-staging \
    -ov -format UDZO \
    "$DMG"
rm -rf dist/dmg-staging

# 4. 签名 DMG
echo "[4/6] 签名 DMG..."
codesign --force --sign "$IDENTITY" --timestamp "$DMG"

# 5. 公证
echo "[5/6] 提交公证（可能需要几分钟）..."
xcrun notarytool submit "$DMG" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

# 6. Staple
echo "[6/6] Staple 公证票据..."
xcrun stapler staple "$DMG"

SIZE=$(du -sh "$DMG" | cut -f1)
echo ""
echo "=== 构建完成 ==="
echo "  DMG: $DMG ($SIZE)"
echo "  ✓ 已签名"
echo "  ✓ 已公证"
echo "  ✓ 已 Staple"
echo ""
echo "用户可直接下载安装，macOS 不会拦截。"
