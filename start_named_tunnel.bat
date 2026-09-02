@echo off
chcp 65001 >nul 2>&1
title Model Detective - Named Tunnel
echo.
echo  ============================================
echo   Model Detective - Cloudflare Named Tunnel
echo   URL: https://detect.model-detective.online
echo  ============================================
echo.

cd /d "d:\Ai工作\model-detective"

REM 检查 Flask 是否已在运行
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [1/2] 启动 Flask...
    start /min "Flask" cmd /c ".venv\Scripts\python.exe run_web.py"
    timeout /t 3 /nobreak >nul
) else (
    echo  [SKIP] Flask 已在运行
)

echo.
echo  [2/2] 启动 Cloudflare 命名隧道...
echo  访问地址: https://detect.model-detective.online
echo  --------------------------------------------
echo.

"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --config "d:\Ai工作\model-detective\.cloudflared\config.yml" run 3afd1108-3572-4fbe-b841-b5f7cd9d23fa

echo.
echo  [INFO] 隧道已断开
echo.
pause
