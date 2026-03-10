@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: build_app.bat — 构建 SitMonitor.exe (Windows CMD 版本)
:: 用法: 双击运行 或 在命令行中执行 build_app.bat

echo === SitMonitor Windows 构建 ===

:: 激活虚拟环境
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

:: 1. 检查 PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [!] PyInstaller 未安装，正在安装...
    pip install pyinstaller
)

:: 2. 生成 .ico 图标
if exist build-resources\SitMonitor.png (
    if not exist build-resources\SitMonitor.ico (
        echo [*] 生成 .ico 图标...
        python -c "from PIL import Image; img=Image.open('build-resources/SitMonitor.png'); img.save('build-resources/SitMonitor.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]); print('    -> build-resources/SitMonitor.ico')"
        if errorlevel 1 echo [!] 图标生成失败，将使用默认图标
    ) else (
        echo [*] 使用已有图标: build-resources\SitMonitor.ico
    )
) else (
    echo [*] 无自定义图标，将使用默认图标
)

:: 3. 检查必需资源
echo [*] 检查资源文件...
set "MISSING=0"
if not exist pose_landmarker_lite.task (
    echo [!] 缺少 pose_landmarker_lite.task，请先下载模型文件
    set "MISSING=1"
)
if not exist face_landmarker.task (
    echo [!] 缺少 face_landmarker.task，请先下载模型文件
    set "MISSING=1"
)
if "%MISSING%"=="1" (
    pause
    exit /b 1
)
echo     ML 模型 OK

:: 4. 清理旧构建
echo [*] 清理旧构建...
if exist build\SitMonitor rmdir /s /q build\SitMonitor
if exist dist\SitMonitor rmdir /s /q dist\SitMonitor

:: 5. PyInstaller 打包
echo [*] 开始 PyInstaller 打包...
python -m PyInstaller SitMonitor_win.spec --noconfirm
if errorlevel 1 (
    echo [!] 构建失败
    pause
    exit /b 1
)

:: 6. 验证
if exist dist\SitMonitor\SitMonitor.exe (
    echo.
    echo === 构建成功 ===
    echo   路径: dist\SitMonitor\
    echo.
    echo 测试运行: dist\SitMonitor\SitMonitor.exe
    echo 打包发布: 将 dist\SitMonitor 文件夹压缩为 zip 即可分发
) else (
    echo [!] 构建失败：dist\SitMonitor\SitMonitor.exe 未生成
    pause
    exit /b 1
)

echo.
pause
