@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo ==========================================
echo      正在检查 Python 环境...
echo ==========================================

:: 尝试检查 python 命令是否存在
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :INSTALL
)

:: 如果 python 不存在，尝试 py 命令 (Windows Launcher)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto :INSTALL
)

:: 如果都找不到，报错并提示
echo.
echo [错误] 电脑上找不到 Python！
echo.
echo 请按照以下步骤解决：
echo 1. 卸载当前的 Python（如果有）。
echo 2. 去官网下载最新的 Python 安装包。
echo 3. 安装时，务必勾选底部的 "Add Python to PATH" (添加到环境变量) 选项！
echo.
pause
exit /b

:INSTALL
echo 检测到 Python: %PYTHON_CMD%
echo.

echo ==========================================
echo      正在安装依赖库 (Pandas)...
echo ==========================================
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败！请检查网络。
    pause
    exit /b
)

echo.
echo ==========================================
echo      正在安装浏览器驱动 (Playwright)...
echo ==========================================
%PYTHON_CMD% -m playwright install
if %errorlevel% neq 0 (
    echo.
    echo [错误] 浏览器驱动安装失败！请检查网络。
    pause
    exit /b
)

echo.
echo ==========================================
echo      安装完成！正在启动爬虫...
echo ==========================================
%PYTHON_CMD% nmpa_spider.py

pause
