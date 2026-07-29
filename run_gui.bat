@echo off
chcp 65001 >nul
title linodl GUI
cd /d "%~dp0"

python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Installing Python requirements...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :end
)

if not exist "frontend\dist\index.html" (
    echo Building React desktop assets...
    pushd frontend
    call npm run build
    if errorlevel 1 (
        popd
        goto :end
    )
    popd
)

echo Starting linodl React desktop UI...
python -m linodl --gui %*

:end
pause
