@echo off
chcp 65001 >nul
title linodl GUI
cd /d "%~dp0"

:: Check if customtkinter is available
python -c "import customtkinter" 2>nul
if errorlevel 1 (
    echo Installing customtkinter...
    pip install customtkinter -q
)

echo Starting linodl GUI...
python -m linodl --gui %*
pause
