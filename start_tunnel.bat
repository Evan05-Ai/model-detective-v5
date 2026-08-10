@echo off
chcp 65001 >nul 2>&1
title Model Detective - Cloudflare Tunnel

REM ============================================================
REM  Model Detective - Cloudflare Tunnel 一键启动脚本
REM
REM  功能：
REM    1. 启动 Flask 应用 (localhost:5000)
REM    2. 启动 Cloudflare Tunnel，获取公网 URL
REM    3. 任何人可通过该 URL 访问你的项目
REM
REM  关闭方法：直接关闭此窗口（或按 Ctrl+C）
REM ============================================================

echo.
echo  ============================================
echo   Model Detective - Cloudflare Tunnel
echo  ============================================
echo.

REM ── 切换到项目目录 ──────────────────────────
cd /d "d:\Ai工作\model-detective"

REM ── 检查虚拟环境 ────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] 找不到 .venv\Scripts\python.exe
    echo  请先创建虚拟环境并安装依赖
    pause
    exit /b 1
)

REM ── 刷新 PATH 以找到 cloudflared ──────────────
set "PATH=%PATH%;C:\Program Files (x86)\cloudflared"

REM ── 检查 cloudflared ─────────────────────────
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] 找不到 cloudflared
    echo  请先运行: winget install cloudflare.cloudflared
    pause
    exit /b 1
)

REM ── 检查端口 5000 是否被占用 ──────────────────
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [WARNING] 端口 5000 已被占用，可能 Flask 已在运行
    echo  跳过 Flask 启动，直接启动隧道...
    echo.
    goto :start_tunnel
)

REM ── 启动 Flask 应用 ──────────────────────────
echo  [1/2] 正在启动 Flask 应用...
start /min "Model Detective Flask" cmd /c ".venv\Scripts\python.exe run_web.py"

REM ── 等待 Flask 就绪 ──────────────────────────
echo  等待 Flask 就绪...
set "wait_count=0"
:wait_flask
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    set /a wait_count+=1
    if %wait_count% lss 10 (
        goto :wait_flask
    )
    echo  [ERROR] Flask 启动超时
    pause
    exit /b 1
)
echo  [OK] Flask 已启动: http://localhost:5000
echo.

REM ── 启动 Cloudflare Tunnel ───────────────────
:start_tunnel
echo  [2/2] 正在启动 Cloudflare Tunnel...
echo  正在获取公网 URL，请稍候...
echo  --------------------------------------------
echo.
cloudflared tunnel --url http://localhost:5000

REM ── 如果 cloudflared 退出 ───────────────────
echo.
echo  [INFO] Tunnel 已断开
echo  按任意键退出...
pause >nul
