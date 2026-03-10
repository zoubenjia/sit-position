@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: service.bat — Windows 服务管理脚本（CMD 版本）
:: 用法: service.bat <命令>
:: 命令: install | uninstall | start | stop | restart | status | update | log

set "SCRIPT_DIR=%~dp0"
set "APP_NAME=SitMonitor"
set "PYTHONW=%SCRIPT_DIR%.venv\Scripts\pythonw.exe"
set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\%APP_NAME%.lnk"
set "LOG_FILE=%SCRIPT_DIR%logs\posture.jsonl"

if "%~1"=="" goto status
if /i "%~1"=="install" goto install
if /i "%~1"=="uninstall" goto uninstall
if /i "%~1"=="start" goto start
if /i "%~1"=="stop" goto stop
if /i "%~1"=="restart" goto restart
if /i "%~1"=="status" goto status
if /i "%~1"=="update" goto update
if /i "%~1"=="log" goto log

echo 用法: service.bat [install^|uninstall^|start^|stop^|restart^|status^|update^|log]
exit /b 1

:install
if not exist "%PYTHONW%" (
    echo [错误] 未找到 %PYTHONW%，请先运行 setup.bat
    exit /b 1
)

:: 创建启动快捷方式（使用 VBScript）
echo Set ws = CreateObject("WScript.Shell") > "%TEMP%\create_shortcut.vbs"
echo Set sc = ws.CreateShortcut("%SHORTCUT%") >> "%TEMP%\create_shortcut.vbs"
echo sc.TargetPath = "%PYTHONW%" >> "%TEMP%\create_shortcut.vbs"
echo sc.Arguments = "-m sit_monitor --tray" >> "%TEMP%\create_shortcut.vbs"
echo sc.WorkingDirectory = "%SCRIPT_DIR%" >> "%TEMP%\create_shortcut.vbs"
echo sc.Description = "Sit Position Monitor" >> "%TEMP%\create_shortcut.vbs"
echo sc.Save >> "%TEMP%\create_shortcut.vbs"
cscript //nologo "%TEMP%\create_shortcut.vbs"
del "%TEMP%\create_shortcut.vbs"
echo [OK] 已安装开机自启动
goto start

:uninstall
call :stop_impl
if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo [OK] 已卸载自启动
) else (
    echo 未安装自启动
)
goto :eof

:start
:: 检查是否已在运行
call :find_process
if defined SIT_PID (
    echo 坐姿监控已在运行 (PID: %SIT_PID%)
    goto :eof
)
start "" /B "%PYTHONW%" -m sit_monitor --tray
timeout /t 2 /nobreak >nul
call :find_process
if defined SIT_PID (
    echo [OK] 已启动 (PID: %SIT_PID%)
) else (
    echo [警告] 启动可能失败，请检查日志
)
goto :eof

:stop
call :stop_impl
goto :eof

:stop_impl
call :find_process
if defined SIT_PID (
    echo 停止进程 PID: %SIT_PID%
    taskkill /PID %SIT_PID% /F >nul 2>&1
    echo [OK] 已停止
) else (
    echo 坐姿监控未在运行
)
goto :eof

:restart
call :stop_impl
timeout /t 1 /nobreak >nul
goto start

:status
call :find_process
if exist "%SHORTCUT%" (
    set "AUTOSTART=已安装"
) else (
    set "AUTOSTART=未安装"
)
if defined SIT_PID (
    echo 状态: 运行中 (PID: %SIT_PID%)
) else (
    echo 状态: 未运行
)
echo 自启动: %AUTOSTART%
goto :eof

:update
echo 检查更新...
cd /d "%SCRIPT_DIR%"
git fetch origin 2>nul
for /f %%a in ('git rev-parse HEAD') do set "LOCAL=%%a"
for /f %%a in ('git rev-parse origin/main') do set "REMOTE=%%a"
if "%LOCAL%"=="%REMOTE%" (
    echo 已是最新版本
    goto :eof
)
echo 发现新版本，正在更新...
git pull origin main
:: 检查依赖是否需要更新
git diff %LOCAL% %REMOTE% --name-only | findstr "requirements.txt" >nul 2>&1
if not errorlevel 1 (
    echo 更新依赖...
    uv pip install --python "%PYTHON%" -r requirements.txt
)
git log %LOCAL%..%REMOTE% --oneline
echo 更新完成，重启服务...
call :stop_impl
timeout /t 1 /nobreak >nul
goto start

:log
if exist "%LOG_FILE%" (
    :: 显示最后 50 行
    "%PYTHON%" -c "lines=open(r'%LOG_FILE%','r',encoding='utf-8').readlines(); [print(l,end='') for l in lines[-50:]]"
) else (
    echo 日志文件不存在: %LOG_FILE%
)
goto :eof

:find_process
set "SIT_PID="
for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe' and commandline like '%%sit_monitor%%' and commandline like '%%--tray%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    set "SIT_PID=%%p"
)
if not defined SIT_PID (
    for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe'" get processid^,commandline 2^>nul ^| findstr "sit_monitor" ^| findstr "--tray"') do (
        set "SIT_PID=%%p"
    )
)
goto :eof
