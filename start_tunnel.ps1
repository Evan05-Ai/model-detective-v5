# ============================================================
#  Model Detective - Cloudflare Tunnel 一键启动脚本 (PowerShell)
#
#  功能：
#    1. 启动 Flask 应用 (localhost:5000)
#    2. 启动 Cloudflare Tunnel，获取公网 URL
#    3. 任何人可通过该 URL 访问你的项目
#
#  用法：
#    .\start_tunnel.ps1              # 快速隧道（临时 URL）
#    .\start_tunnel.ps1 -Named       # 命名隧道（需要 Cloudflare 账号 + 域名）
#
#  关闭方法：按 Ctrl+C 或关闭窗口
# ============================================================

param(
    [switch]$Named,
    [string]$Hostname = "detect.example.com",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "d:\Ai工作\model-detective"

# ── 切换到项目目录 ──────────────────────────
Set-Location $ProjectRoot

# ── 辅助函数 ────────────────────────────────
function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-PortInUse {
    param([int]$PortNum)
    $conn = Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

# ── 标题 ────────────────────────────────────
Write-Header "Model Detective - Cloudflare Tunnel"

# ── 检查虚拟环境 ────────────────────────────
$pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "  [ERROR] 找不到 .venv\Scripts\python.exe" -ForegroundColor Red
    Write-Host "  请先创建虚拟环境并安装依赖" -ForegroundColor Yellow
    exit 1
}

# ── 检查 cloudflared ─────────────────────────
$cfPath = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cfPath) {
    # 尝试常见安装路径
    $cfCommonPaths = @(
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb2d8e3we\cloudflared.exe"
    )
    foreach ($p in $cfCommonPaths) {
        if (Test-Path $p) {
            $env:PATH = "$env:PATH;$(Split-Path $p)"
            $cfPath = Get-Command cloudflared -ErrorAction SilentlyContinue
            if ($cfPath) { break }
        }
    }
}
if (-not $cfPath) {
    Write-Host "  [ERROR] 找不到 cloudflared" -ForegroundColor Red
    Write-Host "  请先运行: winget install cloudflare.cloudflared" -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] cloudflared: $($cfPath.Source)" -ForegroundColor Green
Write-Host "  [OK] Python: $pythonExe" -ForegroundColor Green
Write-Host ""

# ── 检查端口是否被占用 ──────────────────────
$flaskRunning = Test-PortInUse -PortNum $Port

if (-not $flaskRunning) {
    # ── 启动 Flask ───────────────────────────
    Write-Host "  [1/2] 正在启动 Flask 应用 (port $Port)..." -ForegroundColor Yellow

    $flaskJob = Start-Job -ScriptBlock {
        param($py, $root, $port)
        Set-Location $root
        & $py "run_web.py"
    } -ArgumentList $pythonExe, $ProjectRoot, $Port

    # ── 等待 Flask 就绪 ─────────────────────
    $maxWait = 20
    $waited = 0
    while (-not (Test-PortInUse -PortNum $Port) -and $waited -lt $maxWait) {
        Start-Sleep -Seconds 1
        $waited++
    }

    if (-not (Test-PortInUse -PortNum $Port)) {
        Write-Host "  [ERROR] Flask 启动超时 (${maxWait}s)" -ForegroundColor Red
        Receive-Job $flaskJob
        exit 1
    }

    Write-Host "  [OK] Flask 已启动: http://localhost:$Port" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] 端口 $Port 已被占用，Flask 可能已在运行" -ForegroundColor DarkYellow
}

Write-Host ""

# ── 启动 Cloudflare Tunnel ───────────────────
if ($Named) {
    # ── 命名隧道模式 ───────────────────────
    Write-Header "命名隧道模式"

    $tunnelName = "model-detective"
    $credDir = Join-Path $env:USERPROFILE ".cloudflared"

    Write-Host "  隧道名称: $tunnelName" -ForegroundColor Gray
    Write-Host "  域名: $Hostname" -ForegroundColor Gray
    Write-Host ""

    # 检查是否已登录
    $certFile = Join-Path $credDir "cert.pem"
    if (-not (Test-Path $certFile)) {
        Write-Host "  [INFO] 首次使用，需要登录 Cloudflare..." -ForegroundColor Yellow
        Write-Host "  浏览器会打开，请选择你的域名并授权" -ForegroundColor Gray
        cloudflared tunnel login
    }

    # 检查隧道是否已创建
    $tunnelList = cloudflared tunnel list 2>&1
    if ($tunnelList -notmatch $tunnelName) {
        Write-Host "  [INFO] 创建命名隧道..." -ForegroundColor Yellow
        cloudflared tunnel create $tunnelName
    }

    # 获取隧道 ID
    $tunnelInfo = cloudflared tunnel list 2>&1
    $tunnelId = ($tunnelInfo | Select-String $tunnelName).Line -replace "\s+", " " -split " " | Select-Object -First 1
    $credFile = Join-Path $credDir "$tunnelId.json"

    Write-Host "  隧道 ID: $tunnelId" -ForegroundColor Gray

    # 创建配置文件
    $configFile = Join-Path $credDir "config.yml"
    $configContent = @"
tunnel: $tunnelId
credentials-file: $credFile

ingress:
  - hostname: $Hostname
    service: http://localhost:$Port
  - service: http_status:404
"@
    Set-Content -Path $configFile -Value $configContent -Encoding UTF8
    Write-Host "  配置文件: $configFile" -ForegroundColor Gray

    # 配置 DNS
    Write-Host "  [INFO] 配置 DNS 路由..." -ForegroundColor Yellow
    cloudflared tunnel route dns $tunnelName $Hostname 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }

    Write-Host ""
    Write-Host "  [START] 启动命名隧道..." -ForegroundColor Green
    Write-Host "  访问地址: https://$Hostname" -ForegroundColor Cyan
    Write-Host "  --------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""

    cloudflared tunnel run $tunnelName
} else {
    # ── 快速隧道模式 ───────────────────────
    Write-Host "  [2/2] 正在启动 Cloudflare 快速隧道..." -ForegroundColor Yellow
    Write-Host "  正在获取公网 URL，请稍候..." -ForegroundColor Gray
    Write-Host "  --------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""

    cloudflared tunnel --url http://localhost:$Port
}

# ── 清理 ────────────────────────────────────
Write-Host ""
Write-Host "  [INFO] Tunnel 已断开" -ForegroundColor Yellow
if ($flaskJob) {
    Write-Host "  正在关闭 Flask..." -ForegroundColor Gray
    Stop-Job $flaskJob -ErrorAction SilentlyContinue
    Remove-Job $flaskJob -ErrorAction SilentlyContinue
}
Write-Host "  按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
