@echo off
chcp 65001 >nul 2>&1
title Model Detective - 停止服务

REM ============================================================
REM  Model Detective - 停止所有相关进程
REM  关闭 Flask 和 Cloudflare Tunnel
REM ============================================================

echo.
echo  正在停止 Model Detective 相关进程...
echo.

REM ── 停止 Flask ────────────────────────────
echo  [1/2] 停止 Flask...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
    echo  已终止 Flask 进程 (PID: %%a)
)

REM ── 停止 cloudflared ──────────────────────
echo  [2/2] 停止 cloudflared...
taskkill /im cloudflared.exe /f >nul 2>&1
if %errorlevel% equ 0 (
    echo  已终止 cloudflared 进程
) else (
    echo  cloudflared 未在运行
)

REM ── 停止后台 python run_web.py ────────────
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID:"') do (
    wmic process where "ProcessId=%%i" get CommandLine 2>nul | findstr "run_web.py" >nul 2>&1
    if not errorlevel 1 (
        taskkill /pid %%i /f >nul 2>&1
        echo  已终止 Python (PID: %%i, run_web.py)
    )
)

echo.
echo  完成！所有进程已停止。
echo.
pause
