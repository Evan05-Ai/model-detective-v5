@echo off
echo ============================================
echo  Model Detective 服务重启脚本
echo ============================================
echo.

echo 正在重启 ModelDetectiveFlask 服务...
net stop ModelDetectiveFlask 2>nul
timeout /t 2 /nobreak >nul
net start ModelDetectiveFlask
timeout /t 3 /nobreak >nul

echo.
echo 验证服务状态...
sc query ModelDetectiveFlask | findstr "STATE"

echo.
echo 验证端口 5000...
netstat -ano | findstr ":5000"

echo.
echo ============================================
echo  重启完成！请关闭此窗口。
echo ============================================
pause