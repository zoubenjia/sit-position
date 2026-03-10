# build_app.ps1 — 构建 SitMonitor.exe (Windows)
# 用法: powershell -ExecutionPolicy Bypass -File build_app.ps1
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== SitMonitor Windows 构建 ===" -ForegroundColor Cyan

# 1. 激活虚拟环境
$venvActivate = Join-Path $ScriptDir ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
}

# 2. 检查 PyInstaller
$pyinstaller = python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] PyInstaller 未安装，正在安装..." -ForegroundColor Yellow
    uv pip install pyinstaller
}

# 3. 生成 .ico 图标（如果有 PNG 源文件且无 .ico）
$iconSrc = Join-Path $ScriptDir "build-resources\SitMonitor.png"
$iconDst = Join-Path $ScriptDir "build-resources\SitMonitor.ico"
if ((Test-Path $iconSrc) -and -not (Test-Path $iconDst)) {
    Write-Host "[*] 生成 .ico 图标..."
    try {
        python -c @"
from PIL import Image
img = Image.open(r'$iconSrc')
sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save(r'$iconDst', format='ICO', sizes=sizes)
print('    -> $iconDst')
"@
    } catch {
        Write-Host "[!] 图标生成失败，将使用默认图标" -ForegroundColor Yellow
    }
} elseif (Test-Path $iconDst) {
    Write-Host "[*] 使用已有图标: $iconDst"
} else {
    Write-Host "[*] 无自定义图标，将使用默认图标"
}

# 4. 检查必需资源
Write-Host "[*] 检查资源文件..."
$missingModel = $false
foreach ($f in @("pose_landmarker_lite.task", "face_landmarker.task")) {
    $modelPath = Join-Path $ScriptDir $f
    if (-not (Test-Path $modelPath)) {
        Write-Host "[!] 缺少 $f，请先下载模型文件" -ForegroundColor Red
        $missingModel = $true
    }
}
if ($missingModel) { exit 1 }
Write-Host "    ML 模型 OK"

$assetCount = (Get-ChildItem (Join-Path $ScriptDir "sit_monitor\assets\*.png")).Count
Write-Host "    Assets: $assetCount 个图标 OK"

# 5. 清理旧构建
Write-Host "[*] 清理旧构建..."
$buildDir = Join-Path $ScriptDir "build\SitMonitor"
$distDir = Join-Path $ScriptDir "dist\SitMonitor"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }

# 6. PyInstaller 打包
Write-Host "[*] 开始 PyInstaller 打包..."
python -m PyInstaller SitMonitor_win.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] 构建失败" -ForegroundColor Red
    exit 1
}

# 7. 验证
$exePath = Join-Path $ScriptDir "dist\SitMonitor\SitMonitor.exe"
if (Test-Path $exePath) {
    $size = [math]::Round((Get-ChildItem $exePath).Length / 1MB, 1)
    $dirSize = [math]::Round(((Get-ChildItem (Join-Path $ScriptDir "dist\SitMonitor") -Recurse | Measure-Object -Property Length -Sum).Sum) / 1MB, 0)
    Write-Host ""
    Write-Host "=== 构建成功 ===" -ForegroundColor Green
    Write-Host "  路径: dist\SitMonitor\"
    Write-Host "  EXE:  $size MB"
    Write-Host "  总计: ~${dirSize} MB"
    Write-Host ""
    Write-Host "测试运行: .\dist\SitMonitor\SitMonitor.exe"
    Write-Host "打包发布: 将 dist\SitMonitor 文件夹压缩为 zip 即可分发"
} else {
    Write-Host "[!] 构建失败：$exePath 未生成" -ForegroundColor Red
    exit 1
}
