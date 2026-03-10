@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo === 坐姿监控程序 - Windows 环境搭建 ===
echo.

:: --- 检查 Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.12+
    echo   下载: https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo 找到 %%v

:: --- 检查/安装 uv ---
uv --version >nul 2>&1
if errorlevel 1 (
    echo 未找到 uv，正在安装...
    pip install uv
    if errorlevel 1 (
        echo [错误] uv 安装失败
        pause
        exit /b 1
    )
)
echo uv 已就绪

:: --- Python 虚拟环境 ---
if exist .venv (
    echo 虚拟环境已存在，跳过创建
) else (
    echo 创建 Python 虚拟环境...
    uv venv --python 3.12 .venv
    if errorlevel 1 (
        echo [错误] 无法创建虚拟环境
        pause
        exit /b 1
    )
)

:: --- 安装依赖 ---
echo 安装 Python 依赖...
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: --- 下载模型文件（使用 certutil，Windows 自带，无需 Python） ---
if exist pose_landmarker_lite.task (
    echo 姿势模型已存在，跳过下载
) else (
    echo 下载 MediaPipe Pose 模型（约 6MB）...
    certutil -urlcache -split -f "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task" pose_landmarker_lite.task >nul 2>&1
    if errorlevel 1 (
        echo [错误] 模型下载失败，请检查网络连接
        pause
        exit /b 1
    )
    echo 下载完成
)

if exist face_landmarker.task (
    echo 人脸模型已存在，跳过下载
) else (
    echo 下载 MediaPipe Face 模型...
    certutil -urlcache -split -f "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task" face_landmarker.task >nul 2>&1
    if errorlevel 1 (
        echo [警告] 人脸模型下载失败，疲劳检测功能将不可用
    ) else (
        echo 下载完成
    )
)

:: --- 日志目录 ---
if not exist logs mkdir logs

:: --- 安装自启动并启动 ---
echo.
echo 安装开机自启动并启动托盘...
call service.bat install

:: --- 完成 ---
echo.
echo === 搭建完成 ===
echo.
echo [OK] 坐姿监控已在系统托盘启动（看到托盘图标即成功）
echo [OK] 已设置开机自动启动
echo.
echo 常用命令:
echo   service.bat stop       停止
echo   service.bat restart    重启
echo   service.bat update     更新到最新版本
echo   service.bat uninstall  卸载自启动
echo.
pause
