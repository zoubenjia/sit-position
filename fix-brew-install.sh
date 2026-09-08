#!/usr/bin/env bash
# 修复 brew 安装后的闪退（macOS AMFI 拒载）。
#
# 根因：Homebrew 安装后会对 wheel 里的 .dylib 做 relocation（改 install_name/rpath），
# 破坏其 adhoc 代码签名 → AMFI 拒绝加载 → 进程 import 时被 SIGKILL、反复闪退
# （launchctl status=-9）。实测主 .so 未被改动，是 .dylibs/ 下近百个依赖库被改。
#
# 写进 formula 的 install / post_install 都无效（已验证），只能安装后手动跑本脚本。
# 用法：bash fix-brew-install.sh   （每次 brew install/reinstall/upgrade 之后）
set -euo pipefail

SP=$(ls -d /opt/homebrew/Cellar/sit-monitor/*/libexec/lib/python3.12/site-packages 2>/dev/null | sort -V | tail -1)
[ -n "$SP" ] || { echo "未找到 brew 安装的 sit-monitor"; exit 1; }
BP=$(dirname "$(dirname "$(dirname "$SP")")")/bin/python

echo "重新签名: $SP"
n=0
while IFS= read -r f; do
    codesign --force --sign - "$f" 2>/dev/null && n=$((n+1))
done < <(find "$SP" -type f \( -name "*.dylib" -o -name "*.so" \))
echo "已重签 $n 个二进制文件"

echo -n "验证: "
if "$BP" -c "import cv2, PIL.Image, mediapipe, sit_monitor.tray" 2>/dev/null; then
    echo "✓ 全部可加载"
else
    echo "✗ 仍失败，请检查"; exit 1
fi
