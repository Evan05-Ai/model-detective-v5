# ============================================================
#  Model Detective - Windows 服务安装脚本
#
#  功能：
#    将 Flask + Cloudflare Tunnel 注册为 Windows 服务
#    开机自动启动，无需手动开窗口
#
#  用法（需管理员权限）：
#    .\install_service.ps1 -Install    # 安装服务
#    .\install_service.ps1 -Uninstall  # 卸载服务
#    .\install_service.ps1 -Status     # 查看状态
#
#  需要先安装 NSSM:
#    winget install nssm.nssm
# ============================================================

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "d:\Ai工作\model-detective"
$FlaskServiceName = "ModelDetectiveFlask"
$TunnelServiceName = "ModelDetectiveTunnel"

function Test-Administrator {
    $user = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $user.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Get-NssmPath {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssm) { return $nssm.Source }

    # 尝试常见路径
    $paths = @(
        "C:\Program Files\nssm\win64\nssm.exe",
        "C:\Program Files (x86)\nssm\win64\nssm.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\nssm.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

# ── 检查管理员权限 ──────────────────────────
if (-not (Test-Administrator)) {
    Write-Host "  [ERROR] 需要管理员权限运行此脚本" -ForegroundColor Red
    Write-Host "  右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

# ── 状态查询 ────────────────────────────────
if ($Status) {
    Write-Host ""
    Write-Host "  === 服务状态 ===" -ForegroundColor Cyan
    foreach ($svcName in @($FlaskServiceName, $TunnelServiceName)) {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if ($svc) {
            $color = if ($svc.Status -eq "Running") { "Green" } else { "Yellow" }
            Write-Host "  $svcName : $($svc.Status)" -ForegroundColor $color
        } else {
            Write-Host "  $svcName : 未安装" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    exit 0
}

# ── 卸载 ────────────────────────────────────
if ($Uninstall) {
    Write-Host ""
    Write-Host "  正在卸载服务..." -ForegroundColor Yellow

    foreach ($svcName in @($TunnelServiceName, $FlaskServiceName)) {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if ($svc) {
            if ($svc.Status -eq "Running") {
                Write-Host "  停止 $svcName..." -ForegroundColor Gray
                Stop-Service -Name $svcName -Force
            }
            $nssm = Get-NssmPath
            if ($nssm) {
                & $nssm remove $svcName confirm
            }
            Write-Host "  [OK] $svcName 已卸载" -ForegroundColor Green
        } else {
            Write-Host "  [SKIP] $svcName 不存在" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    exit 0
}

# ── 安装 ────────────────────────────────────
if ($Install) {
    Write-Host ""
    Write-Host "  === 安装 Model Detective 服务 ===" -ForegroundColor Cyan
    Write-Host ""

    # 检查 NSSM
    $nssm = Get-NssmPath
    if (-not $nssm) {
        Write-Host "  [ERROR] 找不到 nssm" -ForegroundColor Red
        Write-Host "  请先安装: winget install nssm.nssm" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] nssm: $nssm" -ForegroundColor Green

    # 检查 Python
    $pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        Write-Host "  [ERROR] 找不到 $pythonExe" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Python: $pythonExe" -ForegroundColor Green

    # 检查 cloudflared
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        $env:PATH = "$env:PATH;C:\Program Files (x86)\cloudflared"
        $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    }
    if (-not $cf) {
        Write-Host "  [ERROR] 找不到 cloudflared" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] cloudflared: $($cf.Source)" -ForegroundColor Green
    Write-Host ""

    # ── 1. 安装 Flask 服务 ─────────────────
    Write-Host "  [1/2] 安装 Flask 服务..." -ForegroundColor Yellow

    & $nssm install $FlaskServiceName $pythonExe "run_web.py"
    & $nssm set $FlaskServiceName AppDirectory $ProjectRoot
    & $nssm set $FlaskServiceName AppEnvironmentExtra "PORT=$Port"
    & $nssm set $FlaskServiceName Description "Model Detective Flask Web Application"
    & $nssm set $FlaskServiceName Start "SERVICE_AUTO_START"
    & $nssm set $FlaskServiceName AppStdout (Join-Path $ProjectRoot "logs\flask_stdout.log")
    & $nssm set $FlaskServiceName AppStderr (Join-Path $ProjectRoot "logs\flask_stderr.log")

    # 创建日志目录
    $logDir = Join-Path $ProjectRoot "logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force }

    Write-Host "  [OK] Flask 服务已安装" -ForegroundColor Green

    # ── 2. 安装 Tunnel 服务 ────────────────
    Write-Host "  [2/2] 安装 Cloudflare Tunnel 服务..." -ForegroundColor Yellow

    # 使用快速隧道模式（无需域名）
    # 注意：快速隧道每次重启 URL 会变
    # 如需固定 URL，请使用命名隧道模式
    & $nssm install $TunnelServiceName $cf.Source "tunnel" "--url" "http://localhost:$Port"
    & $nssm set $TunnelServiceName AppDirectory $ProjectRoot
    & $nssm set $TunnelServiceName Description "Cloudflare Tunnel for Model Detective"
    & $nssm set $TunnelServiceName Start "SERVICE_AUTO_START"
    & $nssm set $TunnelServiceName AppStdout (Join-Path $ProjectRoot "logs\tunnel_stdout.log")
    & $nssm set $TunnelServiceName AppStderr (Join-Path $ProjectRoot "logs\tunnel_stderr.log")
    & $nssm set $TunnelServiceName DependOnService $FlaskServiceName

    Write-Host "  [OK] Tunnel 服务已安装" -ForegroundColor Green
    Write-Host ""

    # ── 3. 启动服务 ────────────────────────
    Write-Host "  正在启动服务..." -ForegroundColor Yellow

    Start-Service -Name $FlaskServiceName
    Start-Sleep -Seconds 3
    Start-Service -Name $TunnelServiceName

    Start-Sleep -Seconds 5

    # ── 4. 显示状态 ────────────────────────
    Write-Host ""
    Write-Host "  === 服务状态 ===" -ForegroundColor Cyan
    foreach ($svcName in @($FlaskServiceName, $TunnelServiceName)) {
        $svc = Get-Service -Name $svcName
        $color = if ($svc.Status -eq "Running") { "Green" } else { "Yellow" }
        Write-Host "  $svcName : $($svc.Status)" -ForegroundColor $color
    }
    Write-Host ""
    Write-Host "  日志位置: $ProjectRoot\logs\" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  注意: 快速隧道 URL 每次重启会变" -ForegroundColor Yellow
    Write-Host "  查看当前 URL: type $ProjectRoot\logs\tunnel_stdout.log" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# ── 无参数时显示帮助 ────────────────────────
Write-Host ""
Write-Host "  Model Detective - Windows 服务管理" -ForegroundColor Cyan
Write-Host ""
Write-Host "  用法（需管理员权限）:"
Write-Host "    .\install_service.ps1 -Install     安装并启动服务（开机自启）"
Write-Host "    .\install_service.ps1 -Uninstall   卸载服务"
Write-Host "    .\install_service.ps1 -Status      查看服务状态"
Write-Host ""
Write-Host "  需要先安装 NSSM:"
Write-Host "    winget install nssm.nssm" -ForegroundColor Yellow
Write-Host ""
