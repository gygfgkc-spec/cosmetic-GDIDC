@echo off
cd /d "%~dp0"
chcp 65001 >nul

echo ==========================================
echo      正在尝试检测 Python...
echo ==========================================

:: 优先使用 py 启动器 (Windows 标准推荐)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py -3
    goto :START_INSTALL
)

:: 其次尝试 python 命令
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :START_INSTALL
)

:: 如果都找不到
echo.
echo [严重错误] 电脑上找不到 Python！
echo 系统无法运行 pip 或 python 命令。
echo.
echo 请双击运行文件夹里的 "环境诊断.bat" 查看详细原因。
echo 或者直接重新安装 Python 并勾选 "Add to PATH"。
echo.
pause
exit /b

:START_INSTALL
echo 使用 Python 引擎: %PY_CMD%
echo.

echo ==========================================
echo      正在安装依赖 (Pandas)...
echo ==========================================
%PY_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [安装失败] 无法安装依赖。
    echo 可能是网络问题，也可能是 pip 未正确安装。
    pause
    exit /b
)

echo.
echo ==========================================
echo      正在安装浏览器内核...
echo ==========================================
%PY_CMD% -m playwright install
if %errorlevel% neq 0 (
    echo.
    echo [安装失败] 无法安装浏览器内核。
    pause
    exit /b
)

echo.
echo ==========================================
echo      准备就绪，启动爬虫！
echo ==========================================
%PY_CMD% nmpa_spider.py

pause
