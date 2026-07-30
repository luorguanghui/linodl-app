@echo off
setlocal
chcp 65001 >nul
title Build linodl EXE
cd /d "%~dp0"

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm is required to build the desktop UI.
    exit /b 1
)

echo [1/3] Building React desktop assets...
pushd frontend
if not exist "node_modules" (
    call npm ci
    if errorlevel 1 (
        popd
        exit /b 1
    )
)
call npm run build
if errorlevel 1 (
    popd
    exit /b 1
)
popd

echo [2/3] Installing packaging dependencies...
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [3/3] Packaging Windows application...
python -m PyInstaller --noconfirm --clean --distpath release --workpath build linodl.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete: release\linodl\linodl.exe
exit /b 0
