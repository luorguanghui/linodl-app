@echo off
chcp 65001 >nul
title linodl - linovelib 小说下载器

cd /d "%~dp0"

echo.
echo ========================================
echo   linodl v2.0 - linovelib 小说下载器
echo ========================================
echo.

REM Check if dependencies are installed
python -c "import rich" 2>nul
if %errorlevel% neq 0 (
    echo [安装依赖...]
    pip install -r requirements.txt
    python -m playwright install chromium
    echo.
)

python -m linodl %*
pause
