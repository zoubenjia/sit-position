# service.ps1 — Windows 服务管理脚本
# 用法: powershell -ExecutionPolicy Bypass -File service.ps1 <command>
# 命令: install | uninstall | start | stop | restart | status | update | log

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "update", "log")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "SitMonitor"
$PythonW = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$StartupFolder = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup")
$ShortcutPath = Join-Path $StartupFolder "$AppName.lnk"
$ProcessName = "pythonw"
$LogFile = Join-Path $ScriptDir "logs\posture.jsonl"

function Get-SitMonitorProcess {
    Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
        Where-Object {
            try {
                $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
                $cmdline -and $cmdline -match "sit_monitor" -and $cmdline -match "--tray"
            } catch { $false }
        }
}

function Install-Service {
    # 创建启动文件夹快捷方式
    if (-not (Test-Path $PythonW)) {
        Write-Host "错误: 未找到 $PythonW，请先运行 setup.ps1" -ForegroundColor Red
        exit 1
    }

    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PythonW
    $Shortcut.Arguments = "-m sit_monitor --tray"
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "Sit Position Monitor"
    $Shortcut.Save()

    Write-Host "✅ 已安装开机自启动: $ShortcutPath"

    # 立即启动
    Start-Service-Impl
}

function Uninstall-Service {
    Stop-Service-Impl
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Host "✅ 已卸载自启动"
    } else {
        Write-Host "未安装自启动"
    }
}

function Start-Service-Impl {
    $existing = Get-SitMonitorProcess
    if ($existing) {
        Write-Host "坐姿监控已在运行 (PID: $($existing.Id -join ', '))"
        return
    }

    Start-Process -FilePath $PythonW -ArgumentList "-m", "sit_monitor", "--tray" `
        -WorkingDirectory $ScriptDir -WindowStyle Hidden

    Start-Sleep -Seconds 2
    $proc = Get-SitMonitorProcess
    if ($proc) {
        Write-Host "✅ 已启动 (PID: $($proc.Id -join ', '))"
    } else {
        Write-Host "⚠ 启动可能失败，请检查日志" -ForegroundColor Yellow
    }
}

function Stop-Service-Impl {
    $procs = Get-SitMonitorProcess
    if ($procs) {
        $procs | ForEach-Object {
            Write-Host "停止进程 PID: $($_.Id)"
            $_ | Stop-Process -Force
        }
        Write-Host "✅ 已停止"
    } else {
        Write-Host "坐姿监控未在运行"
    }
}

function Get-ServiceStatus {
    $procs = Get-SitMonitorProcess
    $autostart = Test-Path $ShortcutPath

    if ($procs) {
        Write-Host "状态: 运行中 (PID: $($procs.Id -join ', '))" -ForegroundColor Green
    } else {
        Write-Host "状态: 未运行" -ForegroundColor Yellow
    }

    if ($autostart) {
        Write-Host "自启动: 已安装"
    } else {
        Write-Host "自启动: 未安装"
    }
}

function Update-Service {
    Write-Host "检查更新..."
    Set-Location $ScriptDir

    git fetch origin 2>$null
    $local = git rev-parse HEAD
    $remote = git rev-parse origin/main

    if ($local -eq $remote) {
        Write-Host "已是最新版本"
        return
    }

    Write-Host "发现新版本，正在更新..."
    git pull origin main

    # 检查是否需要更新依赖
    $diff = git diff $local $remote --name-only
    if ($diff -match "requirements.txt") {
        Write-Host "更新依赖..."
        uv pip install --python $Python -r requirements.txt
    }

    $log = git log "$local..$remote" --oneline
    Write-Host "更新完成:" -ForegroundColor Green
    Write-Host $log

    # 重启
    Write-Host "重启服务..."
    Stop-Service-Impl
    Start-Sleep -Seconds 1
    Start-Service-Impl
}

function Show-Log {
    if (Test-Path $LogFile) {
        Get-Content $LogFile -Tail 50
    } else {
        Write-Host "日志文件不存在: $LogFile"
    }
}

# 执行命令
switch ($Command) {
    "install"   { Install-Service }
    "uninstall" { Uninstall-Service }
    "start"     { Start-Service-Impl }
    "stop"      { Stop-Service-Impl }
    "restart"   { Stop-Service-Impl; Start-Sleep -Seconds 1; Start-Service-Impl }
    "status"    { Get-ServiceStatus }
    "update"    { Update-Service }
    "log"       { Show-Log }
}
