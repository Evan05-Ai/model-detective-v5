@echo off
chcp 65001 >nul 2>&1
title Model Detective - 安装开机自启服务

REM ============================================================
REM  将 Flask 应用安装为 Windows 服务（开机自动启动）
REM ============================================================

echo.
echo  ============================================
echo   Model Detective - 安装 Windows 服务
echo  ============================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] 需要管理员权限！
    echo  请右键点击此脚本，选择"以管理员身份运行"
    pause
    exit /b 1
)

cd /d "d:\Ai工作\model-detective"

REM 检查 NSSM
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] 正在安装 NSSM...
    winget install nssm.nssm --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [ERROR] NSSM 安装失败，请手动安装: winget install nssm.nssm
        pause
        exit /b 1
    )
)

echo  [1/3] 正在安装 ModelDetectiveFlask 服务...
nssm install ModelDetectiveFlask "d:\Ai工作\model-detective\.venv\Scripts\python.exe" "run_web.py"
nssm set ModelDetectiveFlask AppDirectory "d:\Ai工作\model-detective"
nssm set ModelDetectiveFlask Description "Model Detective Flask Web Application"
nssm set ModelDetectiveFlask Start SERVICE_AUTO_START

echo  [2/3] 正在启动服务...
net start ModelDetectiveFlask

echo  [3/3] 检查服务状态...
sc query ModelDetectiveFlask | findstr "RUNNING"
if %errorlevel% equ 0 (
    echo.
    echo  [OK] 服务安装成功！
    echo  Flask 将随 Windows 自动启动
    echo  访问地址: https://detect.model-detective.online
    echo.
    echo  管理服务命令:
    echo    net start ModelDetectiveFlask   启动
    echo    net stop ModelDetectiveFlask    停止
    echo    sc delete ModelDetectiveFlask   卸载
) else (
    echo  [WARNING] 服务可能未正常启动，请检查
)

echo.
pause
