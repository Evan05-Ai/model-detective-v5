@echo off
chcp 65001 >nul
title Model Detective Web Server

echo.
echo  ============================================================
echo    Model Detective - Web Server Launcher
echo  ============================================================
echo.

:: Check if port 5000 is already in use
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo  [!] 端口 5000 已被占用，正在关闭旧进程...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 1 /nobreak >nul
    echo  [OK] 旧进程已关闭
    echo.
)

:: Navigate to project directory
cd /d "%~dp0"

:: Start the server
echo  [*] 正在启动 Web 服务器...
echo  [*] 项目目录: %CD%
echo.
echo  ============================================================
echo    浏览器访问:  http://localhost:5000
echo    按 Ctrl+C 停止服务器
echo  ============================================================
echo.

py -3 run_web.py

pause
