@echo off
chcp 65001
cls
title 课评自动生成系统
echo.
echo ==========================================
echo     课评自动生成系统 - 快速启动
echo ==========================================
echo.

:: 切换到项目目录
cd /d "%~dp0"

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请确保 Python 已安装并添加到环境变量
    pause
    exit /b 1
)

echo [1/3] Python 环境检测通过
echo [2/3] 正在启动 Web 服务...
echo [3/3] 服务启动后，请在浏览器访问: http://127.0.0.1:5000
echo.
echo 按 Ctrl+C 可以停止服务
echo.

:: 启动项目
python -B run.py

:: 如果服务异常退出，暂停显示错误信息
if errorlevel 1 (
    echo.
    echo [错误] 服务启动失败，请检查错误信息 above
    pause
)
