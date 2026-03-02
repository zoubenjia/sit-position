# setup.ps1 — Windows 环境搭建脚本
# 用法: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$PythonVersion = "3.12"
$VenvDir = ".venv"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== 坐姿监控程序 - Windows 环境搭建 ===" -ForegroundColor Cyan
Write-Host ""

# --- 检查 Python ---
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "错误: 未找到 Python，请先安装 Python $PythonVersion+" -ForegroundColor Red
    Write-Host "  下载: https://www.python.org/downloads/"
    Write-Host "  安装时请勾选 'Add Python to PATH'"
    exit 1
}

$pyVer = python --version 2>&1
Write-Host "找到 $pyVer"

# --- 检查/安装 uv ---
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Host "未找到 uv，正在安装..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # 刷新环境变量
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        Write-Host "错误: uv 安装后仍找不到，请重新打开终端" -ForegroundColor Red
        exit 1
    }
}
Write-Host "uv 已就绪"

# --- Python 虚拟环境 ---
if (Test-Path $VenvDir) {
    Write-Host "虚拟环境已存在，跳过创建"
} else {
    Write-Host "创建 Python $PythonVersion 虚拟环境..."
    uv venv --python $PythonVersion $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 无法创建虚拟环境" -ForegroundColor Red
        exit 1
    }
}

Write-Host "安装 Python 依赖..."
$pythonExe = Join-Path $ScriptDir "$VenvDir\Scripts\python.exe"
uv pip install --python $pythonExe -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 依赖安装失败" -ForegroundColor Red
    exit 1
}

# --- 模型文件 ---
$ModelFile = Join-Path $ScriptDir "pose_landmarker_lite.task"
if (Test-Path $ModelFile) {
    Write-Host "模型文件已存在，跳过下载"
} else {
    Write-Host "下载 MediaPipe Pose 模型（约 6MB）..."
    $ModelUrl = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
    try {
        Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelFile -UseBasicParsing
        $size = (Get-Item $ModelFile).Length / 1MB
        Write-Host ("模型下载完成 ({0:N1} MB)" -f $size)
    } catch {
        Write-Host "错误: 模型下载失败，请检查网络连接" -ForegroundColor Red
        exit 1
    }
}

# --- 日志目录 ---
$LogDir = Join-Path $ScriptDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# --- 安装自启动并启动 ---
Write-Host ""
Write-Host "安装开机自启动并启动托盘..."
powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "service.ps1") install

# --- 完成 ---
Write-Host ""
Write-Host "=== 搭建完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "✅ 坐姿监控已在系统托盘启动（看到托盘图标即成功）"
Write-Host "✅ 已设置开机自动启动"
Write-Host ""
Write-Host "常用命令:"
Write-Host "  .\service.ps1 stop       # 停止"
Write-Host "  .\service.ps1 restart    # 重启"
Write-Host "  .\service.ps1 update     # 更新到最新版本"
Write-Host "  .\service.ps1 uninstall  # 卸载自启动"
